"""Regressions for two silent-data-loss bugs in the SDK.

Both shipped without raising: one replaced real payload with the string
"[Circular]", the other reported a successful enqueue for an event that was
never sent.
"""

import asyncio

import pytest

from minns._utils import safe_stringify


class TestSafeStringify:
    def test_shared_object_is_not_reported_as_circular(self):
        # The same dict appearing twice side by side is a DAG, not a cycle.
        shared = {"a": 1}
        assert safe_stringify({"x": shared, "y": shared}) == '{"x":{"a":1},"y":{"a":1}}'
        assert safe_stringify([shared, shared]) == '[{"a":1},{"a":1}]'

    def test_repeated_event_in_a_batch_survives(self):
        # process_events([ev, ev]) — a retry list, or a batch that re-sends the
        # same event — used to ship the second copy as "[Circular]".
        ev = {"id": 7, "payload": {"k": "v"}}
        assert safe_stringify({"events": [ev, ev]}) == (
            '{"events":[{"id":7,"payload":{"k":"v"}},{"id":7,"payload":{"k":"v"}}]}'
        )

    def test_true_cycles_are_still_caught(self):
        cyc = {}
        cyc["self"] = cyc
        assert safe_stringify(cyc) == '{"self":"[Circular]"}'

    def test_cyclic_list_does_not_recurse_forever(self):
        lst = []
        lst.append(lst)
        assert safe_stringify(lst) == '["[Circular]"]'

    def test_strips_proto_keys(self):
        out = safe_stringify({"__proto__": 1, "constructor": 2, "ok": 3})
        assert out == '{"ok":3}'


class _AsyncClient:
    """Stand-in for AsyncMinnsClient: process_event is a coroutine function."""

    def __init__(self):
        self.sent = []

    async def process_event(self, event, enable_semantic=False):
        self.sent.append(event)
        return {"success": True}


class TestEnqueueWithAsyncClient:
    def test_async_enqueue_actually_sends(self):
        from minns.builder import EventBuilder

        client = _AsyncClient()

        async def scenario():
            ack = EventBuilder(client, "agent-1", agent_id=1, session_id=1).action("go", {}).enqueue()
            # Acked as queued...
            assert ack["queued"] is True
            assert ack["success"] is True
            # ...and the scheduled task actually runs.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return ack

        asyncio.run(scenario())
        assert len(client.sent) == 1, "the event must reach the client, not be dropped"

    def test_no_running_loop_is_reported_not_acked(self):
        from minns.builder import EventBuilder

        client = _AsyncClient()
        # Called from sync context with an async client: nothing can drive the
        # coroutine, so this must NOT claim the event was queued.
        ack = EventBuilder(client, "agent-1", agent_id=1, session_id=1).action("go", {}).enqueue()
        assert ack["queued"] is False
        assert ack["success"] is False
        assert client.sent == []
