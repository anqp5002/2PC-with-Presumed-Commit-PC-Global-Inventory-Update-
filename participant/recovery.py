from __future__ import annotations


class RecoveryManager:
    """Placeholder for startup recovery from participant JSONL logs."""

    def recover_pending(self) -> dict[str, object]:
        return {
            "status": "stub",
            "message": "READY-state recovery will be implemented in a later phase",
            "recovered_transactions": [],
        }


recovery_manager = RecoveryManager()

