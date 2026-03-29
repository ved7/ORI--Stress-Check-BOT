from copy import deepcopy
from fastapi import HTTPException, status

from .models import Message, SessionDetailResponse, SessionHistoryItem
from .prompts import (
    STEP_DEFINITIONS,
    build_chat_system_prompt,
    build_fallback_question,
    build_kickoff_user_prompt,
)
from .storage import (
    delete_all_session_history,
    delete_session_history,
    ensure_session_exists,
    list_session_history,
    load_session_detail,
    load_session_messages,
    persist_session_snapshot,
)

def validate_turn_limit(messages: list[Message]) -> None:
    if len(messages) <= 20:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Session exceeded the 20-turn prototype limit.",
    )


def validate_turn_sequence(messages: list[Message]) -> None:
    for index, message in enumerate(messages[1:], start=1):
        if message.role != messages[index - 1].role:
            continue
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Messages must alternate between user and assistant turns.",
        )


def clone_messages(messages: list[Message]) -> list[Message]:
    return [message.model_copy(deep=True) for message in messages]


def session_status_for(messages: list[Message]) -> str:
    return "in_progress"


def sync_session_history(session_id: str, client_id: str, client_messages: list[Message]) -> list[Message]:
    validate_turn_limit(client_messages)
    validate_turn_sequence(client_messages)
    if client_messages:
        persist_session_snapshot(
            session_id,
            client_id,
            client_messages,
            detect_step(client_messages),
            session_status_for(client_messages),
        )
        return clone_messages(client_messages)
    stored_messages = load_session_messages(session_id, client_id)
    if stored_messages is not None:
        return clone_messages(stored_messages)
    ensure_session_exists(session_id, client_id, 1)
    return []


def save_assistant_reply(
    session_id: str,
    client_id: str,
    messages: list[Message],
    reply_text: str,
) -> list[Message]:
    updated_messages = [*messages, Message(role="assistant", content=reply_text)]
    validate_turn_limit(updated_messages)
    persist_session_snapshot(
        session_id,
        client_id,
        updated_messages,
        detect_step(updated_messages),
        session_status_for(updated_messages),
    )
    return updated_messages


def save_report(
    session_id: str,
    client_id: str,
    messages: list[Message],
    report_payload: dict,
) -> None:
    persist_session_snapshot(session_id, client_id, messages, 5, "complete", report_payload)


def recent_session_history(client_id: str, limit: int = 4) -> list[SessionHistoryItem]:
    return list_session_history(client_id, limit)


def session_detail(session_id: str, client_id: str) -> SessionDetailResponse:
    return load_session_detail(session_id, client_id)


def delete_saved_session(session_id: str, client_id: str) -> None:
    delete_session_history(session_id, client_id)


def clear_saved_history(client_id: str) -> int:
    return delete_all_session_history(client_id)


def assistant_turn_count(messages: list[Message]) -> int:
    return sum(message.role == "assistant" for message in messages)


def user_turn_count(messages: list[Message]) -> int:
    return sum(message.role == "user" for message in messages)


def detect_step(messages: list[Message]) -> int:
    return min(assistant_turn_count(messages) + 1, 5)


def step_definition_for(messages: list[Message]) -> dict[str, str | int]:
    return deepcopy(STEP_DEFINITIONS[detect_step(messages) - 1])


def is_ready_for_report(messages: list[Message]) -> bool:
    if not messages or messages[-1].role != "user":
        return False
    return assistant_turn_count(messages) >= 5 and user_turn_count(messages) >= 5


def build_chat_messages(messages: list[Message], kickoff_prompt: str) -> list[dict[str, str]]:
    if not messages:
        return [{"role": "user", "content": kickoff_prompt}]
    return [
        {"role": message.role, "content": message.content}
        for message in messages
    ]


def build_transcript(messages: list[Message]) -> str:
    return "\n".join(
        f'{"Ori" if message.role == "assistant" else "User"}: {message.content}'
        for message in messages
    )


def prepare_chat_turn(session_id: str, client_id: str, client_messages: list[Message]) -> dict[str, object]:
    session_messages = sync_session_history(session_id, client_id, client_messages)
    current_step = detect_step(session_messages)
    step_definition = step_definition_for(session_messages)
    return {
        "fallback_text": build_fallback_question(step_definition),
        "llm_messages": build_chat_messages(session_messages, build_kickoff_user_prompt()),
        "session_messages": session_messages,
        "step": current_step,
        "system_prompt": build_chat_system_prompt(step_definition, session_messages),
    }


def persist_chat_turn(
    session_id: str,
    client_id: str,
    session_messages: list[Message],
    reply_text: str,
) -> None:
    safe_reply = reply_text.strip() or "I'm here with you. Tell me a little more."
    save_assistant_reply(session_id, client_id, session_messages, safe_reply)


def prepare_report_turn(
    session_id: str,
    client_id: str,
    client_messages: list[Message],
) -> tuple[str, list[Message]]:
    session_messages = sync_session_history(session_id, client_id, client_messages)
    if not is_ready_for_report(session_messages):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish the fifth Ori check-in step before requesting a report.",
        )
    return build_transcript(session_messages), session_messages


def persist_report_turn(
    session_id: str,
    client_id: str,
    session_messages: list[Message],
    report_payload: dict,
) -> None:
    save_report(session_id, client_id, session_messages, report_payload)
