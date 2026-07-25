"""Concurrent-websocket load driver for the Wizzrobe NiceGUI app.

Mimics what a real browser tab does: GET the page (authenticated), scrape the
client_id NiceGUI minted for that render, then open a socket.io websocket with
the same query params the bundled nicegui.js sends (implicit_handshake=true, so
no separate handshake emit is needed).

Each virtual client == one browser tab == one persistent websocket.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import statistics
import time
import uuid

import httpx
import socketio

CLIENT_ID_RE = re.compile(r"'client_id': '([0-9a-f-]{36})'")


class VClient:
    def __init__(self, base: str, prefix: str, path: str, cookie: str) -> None:
        self.base, self.prefix, self.path, self.cookie = base, prefix, path, cookie
        self.sio: socketio.AsyncClient | None = None
        self.connected = False
        self.error: str | None = None
        self.page_ms = 0.0
        self.ws_ms = 0.0
        self.messages = 0
        self.last_msg_at = 0.0

    async def start(self, http: httpx.AsyncClient) -> None:
        try:
            t0 = time.perf_counter()
            r = await http.get(f'{self.base}{self.path}', headers={'Cookie': self.cookie})
            self.page_ms = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                self.error = f'HTTP {r.status_code}'
                return
            m = CLIENT_ID_RE.search(r.text)
            if not m:
                self.error = 'no client_id in HTML (not a NiceGUI page?)'
                return
            client_id = m.group(1)

            sio = socketio.AsyncClient(reconnection=False)
            self.sio = sio

            @sio.on('*')
            async def _any(event, *args):  # noqa: ANN001
                self.messages += 1
                self.last_msg_at = time.perf_counter()

            q = (
                f'client_id={client_id}&next_message_id=0&implicit_handshake=true'
                f'&document_id={uuid.uuid4()}&tab_id={uuid.uuid4()}'
            )
            t1 = time.perf_counter()
            await sio.connect(
                f'{self.base}?{q}',
                socketio_path=f'{self.prefix}/_nicegui_ws/socket.io',
                transports=['websocket'],
                headers={'Cookie': self.cookie},
                wait_timeout=30,
            )
            self.ws_ms = (time.perf_counter() - t1) * 1000
            self.connected = True
        except Exception as e:  # noqa: BLE001
            self.error = f'{type(e).__name__}: {e}'

    async def stop(self) -> None:
        if self.sio is not None:
            try:
                await self.sio.disconnect()
            except Exception:  # noqa: BLE001
                pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--prefix', default='/t/default')
    ap.add_argument('--path', default='/t/default/')
    ap.add_argument('--cookie-file', default='cookie.txt')
    ap.add_argument('--ramp', type=float, default=0.01, help='seconds between client starts')
    ap.add_argument('--hold', type=float, default=20.0)
    ap.add_argument('--label', default='')
    args = ap.parse_args()

    cookie = open(args.cookie_file).read().strip()
    clients = [VClient(args.base, args.prefix, args.path, cookie) for _ in range(args.n)]

    limits = httpx.Limits(max_connections=args.n + 50, max_keepalive_connections=args.n + 50)
    async with httpx.AsyncClient(timeout=60.0, limits=limits) as http:
        t0 = time.perf_counter()

        async def run(c: VClient, delay: float) -> None:
            await asyncio.sleep(delay)
            await c.start(http)

        await asyncio.gather(*(run(c, i * args.ramp) for i, c in enumerate(clients)))
        ramp_total = time.perf_counter() - t0

        ok = [c for c in clients if c.connected]
        bad = [c for c in clients if not c.connected]
        print(f'=== {args.label or args.path} | requested={args.n} ===')
        print(f'connected      : {len(ok)}/{args.n}')
        print(f'ramp wall time : {ramp_total:.1f}s')
        if ok:
            pages = sorted(c.page_ms for c in ok)
            wss = sorted(c.ws_ms for c in ok)
            def pct(xs, p):
                return xs[min(len(xs) - 1, int(len(xs) * p))]
            print(f'page render ms : p50={statistics.median(pages):.0f} '
                  f'p95={pct(pages, .95):.0f} max={pages[-1]:.0f}')
            print(f'ws connect ms  : p50={statistics.median(wss):.0f} '
                  f'p95={pct(wss, .95):.0f} max={wss[-1]:.0f}')
        if bad:
            errs: dict[str, int] = {}
            for c in bad:
                errs[c.error or '?'] = errs.get(c.error or '?', 0) + 1
            print('failures       :')
            for e, n in sorted(errs.items(), key=lambda kv: -kv[1]):
                print(f'   {n:>4}x {e}')

        # Hold the sockets open so an external observer can sample the server.
        if ok:
            print(f'holding {len(ok)} sockets for {args.hold}s ...', flush=True)
            await asyncio.sleep(args.hold)
            alive = sum(1 for c in ok if c.sio and c.sio.connected)
            print(f'still connected after hold: {alive}/{len(ok)}')
            print(f'push messages received during hold: {sum(c.messages for c in ok)}')

        await asyncio.gather(*(c.stop() for c in clients))


if __name__ == '__main__':
    asyncio.run(main())
