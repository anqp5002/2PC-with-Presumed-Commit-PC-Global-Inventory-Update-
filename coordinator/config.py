from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParticipantConfig:
    site_id: str
    region: str
    base_url: str


COORDINATOR_HOST = "127.0.0.1"
COORDINATOR_PORT = 8000
SERVICE_NAME = "coordinator"

PARTICIPANTS: dict[str, ParticipantConfig] = {
    "site_a": ParticipantConfig("site_a", "North", "http://127.0.0.1:8001"),
    "site_b": ParticipantConfig("site_b", "Central", "http://127.0.0.1:8002"),
    "site_c": ParticipantConfig("site_c", "SouthEast", "http://127.0.0.1:8003"),
    "site_d": ParticipantConfig("site_d", "Mekong", "http://127.0.0.1:8004"),
}

