from __future__ import annotations

from fastapi import FastAPI

from coordinator.config import PARTICIPANTS, SERVICE_NAME
from coordinator.message_counter import message_counter
from coordinator.models import GlobalInventoryUpdateRequest, StubResponse
from coordinator.protocol import protocol

app = FastAPI(
    title="2PC Presumed Commit Coordinator",
    version="0.1.0",
    description="Coordinator API bootstrap for the distributed inventory project.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "participants": {
            site_id: {"region": cfg.region, "base_url": cfg.base_url}
            for site_id, cfg in PARTICIPANTS.items()
        },
    }


@app.post("/transactions/global-inventory-update")
def global_inventory_update(request: GlobalInventoryUpdateRequest):
    return protocol.run_transaction(request)


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str) -> StubResponse:
    state = protocol.get_state(transaction_id)
    return StubResponse(
        service=SERVICE_NAME,
        message="transaction lookup endpoint is ready",
        data={
            "transaction_id": transaction_id,
            "transaction": state.model_dump(mode="json") if state else None,
        },
    )


@app.get("/transactions/{transaction_id}/decision")
def get_transaction_decision(transaction_id: str):
    return protocol.lookup_decision(transaction_id)


@app.get("/metrics/messages")
def get_message_metrics() -> StubResponse:
    return StubResponse(
        service=SERVICE_NAME,
        message="message metrics endpoint is ready",
        data={"counts": message_counter.snapshot()},
    )


@app.post("/metrics/reset")
def reset_message_metrics() -> StubResponse:
    message_counter.reset()
    return StubResponse(
        service=SERVICE_NAME,
        message="message metrics reset endpoint is ready",
    )


@app.post("/debug/forget-transaction/{transaction_id}")
def forget_transaction(transaction_id: str) -> StubResponse:
    removed = protocol.forget_transaction(transaction_id)
    return StubResponse(
        service=SERVICE_NAME,
        message="forget transaction endpoint is ready",
        data={"transaction_id": transaction_id, "removed": removed},
    )
