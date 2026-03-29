from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(str_strip_whitespace=True)


class ChatRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    messages: list[Message] = Field(default_factory=list)
    step: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Ignored by the backend. Step detection happens server-side.",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ReportRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    messages: list[Message] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)


class StressProfile(BaseModel):
    stress_style: str
    primary_stressor: str
    body_signals: str
    coping_pattern: str
    support_need: str


class ReportResponse(BaseModel):
    complete: Literal[True] = True
    profile: StressProfile
    actions: list[str] = Field(..., min_length=3, max_length=3)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class SessionHistoryItem(BaseModel):
    session_id: str
    status: Literal["in_progress", "complete"]
    current_step: int = Field(..., ge=1, le=5)
    created_at: str
    updated_at: str
    completed_at: str | None = None
    questions: list[str] = Field(default_factory=list)
    report: ReportResponse | None = None


class SessionHistoryResponse(BaseModel):
    client_id: str
    sessions: list[SessionHistoryItem] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    client_id: str
    session_id: str
    status: Literal["in_progress", "complete"]
    current_step: int = Field(..., ge=1, le=5)
    created_at: str
    updated_at: str
    completed_at: str | None = None
    messages: list[Message] = Field(default_factory=list)
    report: ReportResponse | None = None


class DeleteSessionResponse(BaseModel):
    deleted: Literal[True] = True
    session_id: str


class ClearHistoryResponse(BaseModel):
    deleted_count: int = Field(..., ge=0)
