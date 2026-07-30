# Wave 1 — An action is never silently lost (F1, F2)

**Read [README.md](README.md) first.** The design decisions there — client-side
honesty, no queue-and-retry, no optimistic UI, tenant-local navigate paths — are
the whole basis of this wave.

**Goal:** on a venue network, the operator can always tell whether the thing they
just tapped happened. And the link a scan produces after a login round trip is the
link that was scanned.

Presentation only. No model, no migration, no service change.

---

## Task 1.1 — A connection state the page actually shows

**Where:** new `theme/connection.py`; CSS beside the existing
`.nicegui-error-popup` block in
[`static/css/styles.css`](../../../static/css/styles.css).

Build one presentation helper — call it `install_connection_watch()` — that a page
calls at build time to get a persistent, visible offline state.

Requirements:

- **Detect from the browser, not the server.** Listen to `window`'s `offline` /
  `online` events *and* `window.socket`'s `disconnect` / `connect`. The window
  events fire immediately when the link drops (and Playwright's offline emulation
  triggers them); the socket events cover the case the audit could not reach — the
  network is up but the server is unreachable, where `navigator.onLine` stays
  `true`. Both are needed; neither alone is sufficient.
- **Tolerate the socket not existing yet.** `window.socket` is assigned in
  `nicegui.js`'s `mounted()`. Attach the socket listeners behind a short retry (or
  from inside a `connect` handler installed once the object appears) and never
  throw if it is missing.
- **Say it in words, in a fixed position.** A banner, not a toast: a toast that
  fired while the page was backgrounded is gone by the time the operator looks.
  Reuse the branding of the framework popup that already exists in this sheet, and
  clear the mobile bottom nav the same way it does
  (`calc(var(--wiz-bottom-nav-h) + env(safe-area-inset-bottom))`).
- **Copy, verbatim:** *"No connection — actions won't be saved. Reconnecting…"*
  and on recovery *"Reconnected."* for two seconds. Say what it means for the
  operator, not what happened to the socket.
- **Toggle a body class** (`wiz-offline`) as the single hook tasks 1.2 and 1.3
  read. One source of truth for "we are offline" per page.

Do **not** hide or replace the framework's `#popup`. It carries the real
"reconnecting, about to reload" moment; this banner is the fast, honest state in
front of it. They will briefly both be visible during a long outage — that is
acceptable and worth confirming looks sane at 390 px.

**Tests:** `tests/theme/test_connection_watch.py` — assert the built markup/script
string contains the banner copy, the `wiz-offline` class, and listeners for all
four events (the source-string style of
`tests/theme/test_station_dialog_copy.py`). A unit test cannot prove the
behaviour; task 1.5 does.

**Docs:** [`docs/reference/frontend.md`](../../reference/frontend.md) — a row in
the `theme/` inventory for the new module.

---

## Task 1.2 — A control that cannot work is visibly refused, not silently eaten

**Where:** [`pages/equipment.py`](../../../pages/equipment.py) actions row
(currently lines 114-121); the action buttons in
[`admin_equipment.py`](../../../pages/admin_tabs/admin_equipment.py)'s
`body-cell-actions` **and** `item` slots;
[`home_tabs/equipment.py`](../../../pages/home_tabs/equipment.py)'s
`checkout_btn` / `checkin_btn` snippets.

Mark every control whose effect requires the socket — Check out, Check in, Edit,
Delete, and the register's row actions — with a class (`wiz-requires-socket`), and
have task 1.1's script disable them while `wiz-offline` is set. A tap on a
disabled control must still explain itself: use `Quasar.Notify.create` directly
from the client script, because `ui.notify` needs the very socket that is down.

**Copy:** *"No connection — not sent. Try again when the banner clears."*

Leave alone the controls that work offline: **Download QR** (a data URI already in
the page) and **Print label** (a new tab, which will fail on its own terms). A
control that still works must not be greyed out.

**Tests:** `tests/theme/` string assertions that each equipment surface's action
markup carries the class — including the `item` slot, which is the one an audit at
390 px actually taps. The desktop and card copies of these buttons are duplicated
HTML today; the test should fail if only one of the two is marked.

**Docs:** the equipment sections of
[`docs/reference/frontend.md`](../../reference/frontend.md) (asset page, admin
register, home tab) gain one sentence about the offline guard.

---

## Task 1.3 — On reconnect, re-read rather than resume

**Where:** [`pages/equipment.py`](../../../pages/equipment.py).

After the socket comes back, the asset page must show the server's state, not the
state it was rendering before the blip. Register a `context.client.on_connect(...)`
handler (`handle_handshake` invokes connect handlers on a reconnect of the same
client, so this fires without a page reload) that refreshes `render_detail`.

Two things to get right and to verify in task 1.5, not assume:

- If the outage outlasted `reconnect_timeout` (3.0 s default) the server has
  already dropped the client and the framework does a **full page reload**
  (`try_reconnect` → `window.location.reload()`), which re-reads anyway. This
  handler only matters for the short blip where the same client survives — say so
  in a comment, since otherwise the next reader will think it is the main path.
- The handler must not fire a stale refresh into a dead client. Follow the
  `background_tasks.create` + `with client:` pattern already used across the
  equipment surfaces.

**Tests:** none that can prove it; covered by task 1.5.

---

## Task 1.4 — Stop double-prefixing the post-login return path

**Where:** [`pages/auth.py`](../../../pages/auth.py) — `_login_as` (the
`ui.navigate.to(referrer)` at the end) and the mock-login already-authenticated
branch (`ui.navigate.to(tenant_home(root_path))`); new pure helper in
[`application/utils/tenant_urls.py`](../../../application/utils/tenant_urls.py).

`referrer_path` is written tenant-qualified by `AuthMiddleware`
(`f'{root_path}{path}'`), and `ui.navigate.to` adds `options.prefix` on top — so a
navigate issued **from a page served under `/t/<slug>`** lands on
`/t/default/t/default/equipment/3`.

Fix:

- Add a pure `strip_root_path(root_path, path)` next to `sanitize_return_path` —
  returns the tenant-local path when `path` sits under `root_path`, and `path`
  unchanged otherwise. Pure, no NiceGUI, unit-tested in
  [`tests/tenancy/test_tenant_urls.py`](../../../tests/tenancy/test_tenant_urls.py).
- Use it at the two `ui.navigate.to` sites above, passing the `root_path` the page
  already has.
- **Leave the `RedirectResponse` sites alone.** An HTTP redirect is not prefixed by
  the client, and `tenant_home(root_path)` is correct there.
- **Leave the real OAuth callback and the handoff claim page alone**, but pin why
  in a comment: both run where `options.prefix` is empty — the callback on the bare
  platform host, the claim on the tenant's own domain — so a fully qualified path
  is right there and a stripped one would be wrong.

**Be honest about the blast radius in the commit message.** In production path
mode, `/oauth/callback` runs on the platform host with an empty prefix, so the
doubling the audit measured reproduces in the **mock-Discord** login loop and in
any future in-tenant navigate handed a prefixed path. It is a dev-loop bug plus a
latent trap, not a live production break — F2's own text says the page renders and
survives a reload. Fix it and pin the framework contract with a test; do not sell
it as more than that.

**Tests:** `tests/tenancy/test_tenant_urls.py` — `strip_root_path` for path mode,
host mode (`root_path=''`), a path outside the prefix, and the `''`/`None`
degenerate cases. Add one assertion that documents the framework contract
(`nicegui.js` prepends `options.prefix` to any absolute path) so a future reader
does not "fix" the helper by re-adding the prefix.

**Docs:** [`docs/reference/authentication.md`](../../reference/authentication.md) —
one line in the post-login return-path description noting that an in-tenant
`ui.navigate.to` takes the tenant-local path.

---

## Task 1.5 — Re-measure the blip, and the round trip

Repeat the audit's own two procedures and write the results into the wave's commit
message in its format.

**Offline procedure** (a real checked-out asset, 390×844, as `staff_user`):

| Step | Expected after this wave |
|---|---|
| Go offline, click **Check in** | banner within ~1 s; button disabled; a *"not sent"* notice on tap |
| Wait 4 s | banner still up (not a toast that expired) |
| Reconnect, wait 5 s | *"Reconnected."*, controls live again, status re-read from the server |

Also run the case the audit could not: **server unreachable, link up** (stop the
app, keep the network) — the banner must still appear, via the socket
`disconnect` path rather than the window `offline` event.

**Login round trip:** scan `/t/default/equipment/3` signed out → log in → assert
the landed URL is exactly `/t/default/equipment/3`.

Screenshot both widths for the asset page and the register with the banner
showing; confirm the banner does not cover the action row or the bottom nav at
390 px.
