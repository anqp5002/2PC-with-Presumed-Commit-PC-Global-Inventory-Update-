from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx

try:
    from scripts.init_databases import init_all_databases
    from scripts.data_config import DATA_DIR
except ModuleNotFoundError:
    from init_databases import init_all_databases
    from data_config import DATA_DIR


MESSAGE_COUNT_CSV = DATA_DIR / "message_counts.csv"
MESSAGE_COUNT_JSON = DATA_DIR / "message_counts.json"


@dataclass(frozen=True)
class MetricCase:
    case_name: str
    mode: str
    expected_total: int
    expected_decision: str
    abort_site_d: bool = False


CASES = [
    MetricCase("PA commit", "PA_COMPARISON", 16, "COMMIT"),
    MetricCase("PC without ACD commit", "PC_NO_ACD", 12, "COMMIT"),
    MetricCase("PC with ACD commit", "PC_WITH_ACD", 16, "COMMIT"),
    MetricCase("PA abort", "PA_COMPARISON", 12, "ABORT", abort_site_d=True),
    MetricCase("PC abort", "PC_WITH_ACD", 16, "ABORT", abort_site_d=True),
]

MESSAGE_COLUMNS = [
    "PREPARE",
    "VOTE_COMMIT",
    "VOTE_ABORT",
    "GLOBAL_COMMIT",
    "GLOBAL_ABORT",
    "ACK_COMMIT",
    "ACK_ABORT",
]


def _commit_updates() -> list[dict[str, object]]:
    return [
        {
            "inventory_id": "INV-000001",
            "warehouse_id": "WH001",
            "region": "North",
            "delta_quantity": -1,
        },
        {
            "inventory_id": "INV-001251",
            "warehouse_id": "WH006",
            "region": "Central",
            "delta_quantity": -1,
        },
        {
            "inventory_id": "INV-002501",
            "warehouse_id": "WH011",
            "region": "SouthEast",
            "delta_quantity": -1,
        },
        {
            "inventory_id": "INV-003751",
            "warehouse_id": "WH016",
            "region": "Mekong",
            "delta_quantity": -1,
        },
    ]


def _updates_for_case(metric_case: MetricCase) -> list[dict[str, object]]:
    updates = _commit_updates()
    if metric_case.abort_site_d:
        updates[-1] = {
            **updates[-1],
            "delta_quantity": -999999,
        }
    return updates


def _post(client: httpx.Client, path: str, payload: dict | None = None) -> dict:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def _get(client: httpx.Client, path: str) -> dict:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def run_case(
    client: httpx.Client,
    metric_case: MetricCase,
    reset_databases: bool = True,
) -> dict[str, object]:
    if reset_databases:
        init_all_databases(reset=True)

    _post(client, "/metrics/reset")
    transaction_id = f"T-metrics-{uuid4().hex[:10]}"
    transaction = _post(
        client,
        "/transactions/global-inventory-update",
        {
            "transaction_id": transaction_id,
            "mode": metric_case.mode,
            "updates": _updates_for_case(metric_case),
        },
    )
    metrics = _get(client, "/metrics/messages")["data"]["counts"]
    row = {
        "case_name": metric_case.case_name,
        "mode": metric_case.mode,
        "transaction_id": transaction_id,
        "decision": transaction.get("decision"),
        "expected_decision": metric_case.expected_decision,
        "expected_total": metric_case.expected_total,
        "actual_total": metrics.get("TOTAL", 0),
        "matches_expected": metrics.get("TOTAL", 0) == metric_case.expected_total
        and transaction.get("decision") == metric_case.expected_decision,
    }
    for message_type in MESSAGE_COLUMNS:
        row[message_type] = metrics.get(message_type, 0)
    return row


def collect_metrics(
    coordinator_url: str,
    output_csv: Path = MESSAGE_COUNT_CSV,
    output_json: Path = MESSAGE_COUNT_JSON,
    reset_databases: bool = True,
) -> list[dict[str, object]]:
    with httpx.Client(base_url=coordinator_url, timeout=10.0) as client:
        rows = [
            run_case(client, metric_case, reset_databases=reset_databases)
            for metric_case in CASES
        ]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_name",
        "mode",
        "transaction_id",
        "decision",
        "expected_decision",
        *MESSAGE_COLUMNS,
        "actual_total",
        "expected_total",
        "matches_expected",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect PA vs PC message-count metrics from the running coordinator."
    )
    parser.add_argument(
        "--coordinator-url",
        default="http://127.0.0.1:8000",
        help="Coordinator base URL.",
    )
    parser.add_argument(
        "--no-reset-databases",
        action="store_true",
        help="Do not re-import SQLite databases before each metric case.",
    )
    args = parser.parse_args()

    rows = collect_metrics(
        coordinator_url=args.coordinator_url,
        reset_databases=not args.no_reset_databases,
    )
    for row in rows:
        print(
            f"{row['case_name']}: total={row['actual_total']} "
            f"expected={row['expected_total']} decision={row['decision']} "
            f"match={row['matches_expected']}"
        )
    print(f"Wrote {MESSAGE_COUNT_CSV}")
    print(f"Wrote {MESSAGE_COUNT_JSON}")


if __name__ == "__main__":
    main()
