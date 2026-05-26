from __future__ import annotations

from collections import Counter


class MessageCounter:
    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def increment(self, message_type: str, amount: int = 1) -> None:
        self._counts[message_type] += amount

    def snapshot(self) -> dict[str, int]:
        snapshot = dict(self._counts)
        snapshot["TOTAL"] = sum(self._counts.values())
        return snapshot

    def reset(self) -> None:
        self._counts.clear()


message_counter = MessageCounter()
