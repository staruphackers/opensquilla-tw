import pytest

from opensquilla.session.models import MemoryDurableReceipt
from opensquilla.session.storage import SessionStorage


async def test_memory_durable_receipt_upsert_is_idempotent(tmp_path):
    storage = await SessionStorage.open(tmp_path / "sessions.db")
    try:
        receipt = MemoryDurableReceipt(
            receipt_id="r1",
            session_key="agent:main:webchat:abc",
            session_id="session-1",
            turn_id="turn-1",
            scope="checkpoint",
            source_path="memory/.checkpoints/agent-main-webchat-abc/turn-1.jsonl",
            target_path=None,
            content_hash="h1",
            idempotency_key="checkpoint:agent:main:webchat:abc:turn-1:h1",
            status="checkpoint_saved",
            reason=None,
            attempt_count=0,
            next_retry_at_ms=None,
        )

        await storage.upsert_memory_durable_receipt(receipt)
        await storage.upsert_memory_durable_receipt(receipt)

        rows = await storage.list_memory_durable_receipts(
            session_key="agent:main:webchat:abc"
        )
        assert len(rows) == 1
        assert rows[0].status == "checkpoint_saved"
    finally:
        await storage.close()


async def test_memory_durable_receipt_filters_and_update(tmp_path):
    storage = await SessionStorage.open(tmp_path / "sessions.db")
    try:
        receipt = MemoryDurableReceipt(
            receipt_id="r2",
            session_key="agent:main:webchat:abc",
            session_id="session-1",
            turn_id="turn-2",
            scope="checkpoint",
            source_path="memory/.checkpoints/agent-main-webchat-abc/turn-2.jsonl",
            target_path=None,
            content_hash="h2",
            idempotency_key="checkpoint:agent:main:webchat:abc:turn-2:h2",
            status="checkpoint_failed",
            reason="write failed",
            attempt_count=1,
            next_retry_at_ms=None,
        )

        saved = await storage.upsert_memory_durable_receipt(receipt)
        updated = await storage.update_memory_durable_receipt(
            saved.receipt_id,
            status="checkpoint_saved",
            reason=None,
            attempt_count=2,
            next_retry_at_ms=123,
        )

        assert updated.status == "checkpoint_saved"
        assert updated.reason is None
        assert updated.attempt_count == 2
        assert updated.next_retry_at_ms == 123

        by_status = await storage.list_memory_durable_receipts(
            session_key="agent:main:webchat:abc",
            status="checkpoint_saved",
        )
        by_idempotency = await storage.list_memory_durable_receipts(
            idempotency_key="checkpoint:agent:main:webchat:abc:turn-2:h2",
        )

        assert [row.receipt_id for row in by_status] == ["r2"]
        assert [row.receipt_id for row in by_idempotency] == ["r2"]

        with pytest.raises(ValueError):
            await storage.update_memory_durable_receipt(saved.receipt_id, unknown=True)
        with pytest.raises(KeyError):
            await storage.update_memory_durable_receipt("missing", status="failed")
    finally:
        await storage.close()
