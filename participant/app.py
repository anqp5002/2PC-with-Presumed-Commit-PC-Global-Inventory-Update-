from __future__ import annotations

from fastapi import FastAPI

from participant.config import get_settings
from participant.inventory_store import inventory_store
from participant.models import (
    DebugFlagResponse,
    PrepareRequest,
    StubResponse,
    TransactionDecisionRequest,
)
from participant.recovery import recovery_manager

settings = get_settings()

app = FastAPI(
    title=f"2PC Participant {settings.site_id}",
    version="0.1.0",
    description="Participant API bootstrap for the distributed inventory project.",
)

debug_flags = {
    "crash_after_ready": False,
    "crash_after_global_commit": False,
}


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.site_id,
        "region": settings.region,
        "coordinator_url": settings.coordinator_url,
    }


@app.post("/prepare")
def prepare(request: PrepareRequest) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="prepare endpoint is ready",
        data={
            "transaction_id": request.transaction_id,
            "mode": request.mode,
            "update_count": len(request.updates),
            "would_vote": "VOTE_COMMIT",
        },
    )


@app.post("/global-commit")
def global_commit(request: TransactionDecisionRequest) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="global commit endpoint is ready",
        data={"transaction_id": request.transaction_id, "mode": request.mode},
    )


@app.post("/global-abort")
def global_abort(request: TransactionDecisionRequest) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="global abort endpoint is ready",
        data={"transaction_id": request.transaction_id, "mode": request.mode},
    )


@app.post("/recover-pending")
def recover_pending() -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="recover pending endpoint is ready",
        data=recovery_manager.recover_pending(),
    )


@app.post("/debug/crash-after-ready")
def set_crash_after_ready(enabled: bool = True) -> DebugFlagResponse:
    debug_flags["crash_after_ready"] = enabled
    return DebugFlagResponse(
        service=settings.site_id,
        flag="crash_after_ready",
        enabled=enabled,
    )


@app.post("/debug/crash-after-global-commit")
def set_crash_after_global_commit(enabled: bool = True) -> DebugFlagResponse:
    debug_flags["crash_after_global_commit"] = enabled
    return DebugFlagResponse(
        service=settings.site_id,
        flag="crash_after_global_commit",
        enabled=enabled,
    )


@app.get("/inventory/{inventory_id}")
def get_inventory(inventory_id: str) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="inventory lookup endpoint is ready",
        data=inventory_store.get_inventory_item(inventory_id),
    )


@app.get("/logs/{transaction_id}")
def get_logs(transaction_id: str) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="transaction log lookup endpoint is ready",
        data={
            "transaction_id": transaction_id,
            "logs": [],
            "note": "JSONL participant logs will be implemented in a later phase",
        },
    )

