from __future__ import annotations

import os
from dataclasses import dataclass


SITE_REGIONS = {
    "site_a": "North",
    "site_b": "Central",
    "site_c": "SouthEast",
    "site_d": "Mekong",
}

SITE_PORTS = {
    "site_a": 8001,
    "site_b": 8002,
    "site_c": 8003,
    "site_d": 8004,
}


@dataclass(frozen=True)
class ParticipantSettings:
    site_id: str
    region: str
    port: int
    coordinator_url: str


def get_settings() -> ParticipantSettings:
    site_id = os.getenv("SITE_ID", "site_a")
    region = os.getenv("REGION", SITE_REGIONS.get(site_id, "Unknown"))
    port = int(os.getenv("PORT", str(SITE_PORTS.get(site_id, 8001))))
    coordinator_url = os.getenv("COORDINATOR_URL", "http://127.0.0.1:8000")
    return ParticipantSettings(
        site_id=site_id,
        region=region,
        port=port,
        coordinator_url=coordinator_url,
    )

