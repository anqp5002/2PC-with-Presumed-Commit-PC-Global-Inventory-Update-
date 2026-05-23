from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TransactionMode(StrEnum):
    PC_WITH_ACD = "PC_WITH_ACD"
    PC_NO_ACD = "PC_NO_ACD"
    PA_COMPARISON = "PA_COMPARISON"


class ParticipantState(StrEnum):
    INIT = "INIT"
    READY = "READY"
    COMMIT = "COMMIT"
    ABORT = "ABORT"


class MessageType(StrEnum):
    PREPARE = "PREPARE"
    VOTE_COMMIT = "VOTE_COMMIT"
    VOTE_ABORT = "VOTE_ABORT"
    GLOBAL_COMMIT = "GLOBAL_COMMIT"
    GLOBAL_ABORT = "GLOBAL_ABORT"
    ACK_COMMIT = "ACK_COMMIT"
    ACK_ABORT = "ACK_ABORT"
    RECOVERY_QUERY = "RECOVERY_QUERY"
    RECOVERY_DECISION = "RECOVERY_DECISION"


class InventoryUpdateItem(BaseModel):
    inventory_id: str = Field(..., examples=["INV-000001"])
    warehouse_id: str = Field(..., examples=["WH001"])
    region: str = Field(..., examples=["North"])
    delta_quantity: int = Field(..., examples=[-5])


class PrepareRequest(BaseModel):
    transaction_id: str
    mode: TransactionMode = TransactionMode.PC_WITH_ACD
    updates: list[InventoryUpdateItem]


class TransactionDecisionRequest(BaseModel):
    transaction_id: str
    mode: TransactionMode = TransactionMode.PC_WITH_ACD


class DebugFlagResponse(BaseModel):
    status: str = "stub"
    service: str
    flag: str
    enabled: bool


class StubResponse(BaseModel):
    status: str = "stub"
    service: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)

