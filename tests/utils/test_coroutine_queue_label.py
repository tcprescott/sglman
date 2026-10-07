"""``coroutine_label`` names a queued call by what it runs, not by its wrapper."""

from application.utils.coroutine_queue import coroutine_label


async def send_dm(user_id: int) -> None:
    return None


async def _run_in_tenant_scope(coro, tenant_id):
    await coro


def test_plain_coroutine_uses_its_own_name():
    coro = send_dm(1)
    try:
        assert coroutine_label(coro) == 'send_dm'
    finally:
        coro.close()


def test_wrapper_names_the_inner_call():
    inner = send_dm(1)
    outer = _run_in_tenant_scope(inner, 3)
    try:
        assert coroutine_label(outer) == '_run_in_tenant_scope(send_dm)'
    finally:
        outer.close()
        inner.close()
