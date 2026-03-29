import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from .conversation import (
    clear_saved_history,
    delete_saved_session,
    persist_chat_turn,
    persist_report_turn,
    prepare_chat_turn,
    prepare_report_turn,
    recent_session_history,
    session_detail,
)
from .db import init_database
from .llm import OpenAIGateway
from .models import (
    ChatRequest,
    ClearHistoryResponse,
    DeleteSessionResponse,
    HealthResponse,
    ReportRequest,
    SessionDetailResponse,
    ReportResponse,
    SessionHistoryResponse,
)

logging.basicConfig(level=logging.INFO)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="Ori Stress Check-In API")
gateway = OpenAIGateway()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def encode_sse(event_name: str, payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_name}\ndata: {serialized}\n\n"


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()


@app.on_event("startup")
async def startup_app() -> None:
    init_database()


@app.on_event("shutdown")
async def shutdown_gateway() -> None:
    await gateway.aclose()


@app.post("/chat")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    chat_turn = prepare_chat_turn(request.session_id, request.client_id, request.messages)

    async def event_stream():
        yield encode_sse("meta", {"step": chat_turn["step"], "ready_for_report": False})
        full_reply = ""
        async for text_chunk in gateway.stream_chat(
            chat_turn["system_prompt"],
            chat_turn["llm_messages"],
            chat_turn["fallback_text"],
        ):
            full_reply += text_chunk
            yield encode_sse("token", {"text": text_chunk})
        persist_chat_turn(request.session_id, request.client_id, chat_turn["session_messages"], full_reply)
        yield encode_sse(
            "done",
            {"step": chat_turn["step"], "ready_for_report": chat_turn["step"] == 5},
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/report", response_model=ReportResponse)
async def build_report(request: ReportRequest) -> ReportResponse:
    transcript, session_messages = prepare_report_turn(request.session_id, request.client_id, request.messages)
    report_payload = await gateway.generate_report(transcript, session_messages)
    persist_report_turn(request.session_id, request.client_id, session_messages, report_payload)
    return ReportResponse.model_validate(report_payload)


@app.get("/history/{client_id}", response_model=SessionHistoryResponse)
async def history(client_id: str) -> SessionHistoryResponse:
    return SessionHistoryResponse(client_id=client_id, sessions=recent_session_history(client_id))


@app.get("/history/{client_id}/{session_id}", response_model=SessionDetailResponse)
async def history_detail(client_id: str, session_id: str) -> SessionDetailResponse:
    return session_detail(session_id, client_id)


@app.delete("/history/{client_id}/{session_id}", response_model=DeleteSessionResponse)
async def delete_history_detail(client_id: str, session_id: str) -> DeleteSessionResponse:
    delete_saved_session(session_id, client_id)
    return DeleteSessionResponse(session_id=session_id)


@app.delete("/history/{client_id}", response_model=ClearHistoryResponse)
async def delete_history(client_id: str) -> ClearHistoryResponse:
    return ClearHistoryResponse(deleted_count=clear_saved_history(client_id))
