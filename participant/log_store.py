from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from participant.models import LogRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ParticipantLogStore:
    def __init__(self, site_id: str, path: Path | None = None) -> None:
        self.site_id = site_id
        self.path = path or (
            PROJECT_ROOT / "runtime" / site_id / f"{site_id}_log.jsonl"
        )

    def append(
        self,
        transaction_id: str,
        state: str,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> LogRecord:
        payload = payload or {}
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        record = LogRecord(
            transaction_id=transaction_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            site_id=self.site_id,
            state=str(state),
            event=str(event),
            payload_hash=sha256(payload_json.encode("utf-8")).hexdigest(),
            payload=payload,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as log_file:
            log_file.write(record.model_dump_json() + "\n")
        return record

    def read_all(self) -> list[LogRecord]:
        if not self.path.exists():
            return []
        records: list[LogRecord] = []
        with self.path.open("r", encoding="utf-8") as log_file:
            for line in log_file:
                line = line.strip()
                if line:
                    records.append(LogRecord.model_validate_json(line))
        return records

    def read_by_transaction(self, transaction_id: str) -> list[LogRecord]:
        return [
            record for record in self.read_all()
            if record.transaction_id == transaction_id
        ]

    def has_event(self, transaction_id: str, event: str) -> bool:
        return any(
            record.event == event
            for record in self.read_by_transaction(transaction_id)
        )

    def has_any_event(self, transaction_id: str, events: set[str]) -> bool:
        return any(
            record.event in events
            for record in self.read_by_transaction(transaction_id)
        )

    def ready_transactions_without_final_state(self) -> list[str]:
        transactions: dict[str, set[str]] = {}
        for record in self.read_all():
            transactions.setdefault(record.transaction_id, set()).add(record.event)

        final_events = {
            "LOCAL_ABORT",
            "APPLIED_COMMIT",
            "ROLLED_BACK",
        }
        return sorted(
            transaction_id
            for transaction_id, events in transactions.items()
            if "READY" in events and not events.intersection(final_events)
        )

