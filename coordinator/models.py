from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TransactionMode(StrEnum):
    PC_WITH_ACD = "PC_WITH_ACD"
    PC_NO_ACD = "PC_NO_ACD"
    PA_COMPARISON = "PA_COMPARISON"


class CoordinatorState(StrEnum):
    INIT = "INIT"
    WAIT = "WAIT"
    COMMIT = "COMMIT"
    ABORT = "ABORT"
    END = "END"


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


class Decision(StrEnum):
    COMMIT = "COMMIT"
    ABORT = "ABORT"
    NOT_FOUND = "NOT_FOUND"


class InventoryUpdateItem(BaseModel):
    inventory_id: str = Field(..., examples=["INV-000001"])
    warehouse_id: str = Field(..., examples=["WH001"])
    region: str = Field(..., examples=["North"])
    delta_quantity: int = Field(..., examples=[-5])


class GlobalInventoryUpdateRequest(BaseModel):
    transaction_id: str | None = Field(default=None, examples=["T-1700812345"])
    mode: TransactionMode = TransactionMode.PC_WITH_ACD
    updates: list[InventoryUpdateItem]


class PrepareRequest(BaseModel):
    transaction_id: str
    mode: TransactionMode = TransactionMode.PC_WITH_ACD
    updates: list[InventoryUpdateItem]


class DecisionResponse(BaseModel):
    transaction_id: str
    decision: Decision


class TransactionDecisionRequest(BaseModel):
    transaction_id: str
    mode: TransactionMode = TransactionMode.PC_WITH_ACD


class VoteResponse(BaseModel):
    transaction_id: str
    site_id: str
    message_type: MessageType
    state: ParticipantState
    reason: str | None = None


class AckResponse(BaseModel):
    transaction_id: str
    site_id: str
    message_type: MessageType
    state: ParticipantState
    reason: str | None = None


class TransactionStateResponse(BaseModel):
    transaction_id: str
    mode: TransactionMode
    state: CoordinatorState
    participants: list[str]
    votes: dict[str, str] = Field(default_factory=dict)
    acks: dict[str, str] = Field(default_factory=dict)
    decision: Decision | None = None
    reason: str | None = None


class LogRecord(BaseModel):
    transaction_id: str
    timestamp: str
    site_id: str
    state: str
    event: str
    payload_hash: str
    payload: dict[str, Any] = Field(default_factory=dict)


class StubResponse(BaseModel):
    status: str = "stub"
    service: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
