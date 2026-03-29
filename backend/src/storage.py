import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from .db import database_available, disable_database, get_connection
from .models import Message, ReportResponse, SessionDetailResponse, SessionHistoryItem

logger = logging.getLogger(__name__)

ACTIVE_CACHE_TTL = timedelta(minutes=30)
HISTORY_CACHE_TTL = timedelta(minutes=2)
ACTIVE_SESSION_CACHE: dict[str, dict[str, object]] = {}
HISTORY_CACHE: dict[str, dict[str, object]] = {}
FALLBACK_SESSION_STORE: dict[str, dict[str, object]] = {}


def utc_now() -> datetime:
    return datetime.now(UTC)


def evict_stale_cache_entries() -> None:
    active_cutoff = utc_now() - ACTIVE_CACHE_TTL
    history_cutoff = utc_now() - HISTORY_CACHE_TTL
    remove_expired_entries(ACTIVE_SESSION_CACHE, active_cutoff)
    remove_expired_entries(HISTORY_CACHE, history_cutoff)


def remove_expired_entries(cache: dict[str, dict[str, object]], cutoff: datetime) -> None:
    expired_keys = [key for key, value in cache.items() if value["updated_at"] < cutoff]
    for key in expired_keys:
        cache.pop(key, None)


def clone_messages(messages: list[Message]) -> list[Message]:
    return [message.model_copy(deep=True) for message in messages]


def ensure_session_owner(row_client_id: str, client_id: str) -> None:
    if row_client_id == client_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This session belongs to a different browser client.",
    )


def set_session_cache(
    session_id: str,
    client_id: str,
    messages: list[Message],
    created_at: str,
    updated_at: str,
) -> None:
    ACTIVE_SESSION_CACHE[session_id] = {
        "client_id": client_id,
        "created_at": created_at,
        "messages": clone_messages(messages),
        "updated_at": datetime.fromisoformat(updated_at),
    }


def get_cached_session_messages(session_id: str, client_id: str) -> list[Message] | None:
    cached_session = ACTIVE_SESSION_CACHE.get(session_id)
    if cached_session is None:
        return None
    ensure_session_owner(str(cached_session["client_id"]), client_id)
    cached_session["updated_at"] = utc_now()
    return clone_messages(cached_session["messages"])


def invalidate_history_cache(client_id: str) -> None:
    HISTORY_CACHE.pop(client_id, None)


def fallback_session_ids_for_client(client_id: str) -> list[str]:
    return [
        session_id
        for session_id, record in FALLBACK_SESSION_STORE.items()
        if str(record["client_id"]) == client_id
    ]


def discard_session_from_memory(session_id: str) -> None:
    ACTIVE_SESSION_CACHE.pop(session_id, None)
    FALLBACK_SESSION_STORE.pop(session_id, None)


def discard_sessions_from_memory(session_ids: list[str]) -> None:
    for session_id in session_ids:
        discard_session_from_memory(session_id)


def fallback_session_record(session_id: str, client_id: str) -> dict[str, object] | None:
    record = FALLBACK_SESSION_STORE.get(session_id)
    if record is None:
        return None
    ensure_session_owner(str(record["client_id"]), client_id)
    return record


def fallback_session_timestamps(session_id: str, status_value: str) -> tuple[str, str | None]:
    created_at = utc_now().isoformat()
    completed_at = utc_now().isoformat() if status_value == "complete" else None
    record = FALLBACK_SESSION_STORE.get(session_id)
    if record is None:
        return created_at, completed_at
    preserved_completion = str(record["completed_at"]) if status_value == "complete" else None
    return str(record["created_at"]), preserved_completion or completed_at


def set_fallback_session_record(
    session_id: str,
    client_id: str,
    messages: list[Message],
    current_step: int,
    status_value: str,
    created_at: str,
    updated_at: str,
    completed_at: str | None,
    report_json: str | None,
) -> None:
    FALLBACK_SESSION_STORE[session_id] = {
        "client_id": client_id,
        "messages": clone_messages(messages),
        "status": status_value,
        "current_step": current_step,
        "created_at": created_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "report_json": report_json,
    }


def questions_from_messages(messages: list[Message]) -> list[str]:
    return [message.content for message in messages if message.role == "assistant"]


def build_history_item_from_record(session_id: str, record: dict[str, object]) -> SessionHistoryItem:
    messages = clone_messages(record["messages"]) if isinstance(record["messages"], list) else []
    return SessionHistoryItem(
        session_id=session_id,
        status=str(record["status"]),
        current_step=int(record["current_step"]),
        created_at=str(record["created_at"]),
        updated_at=str(record["updated_at"]),
        completed_at=str(record["completed_at"]) if record["completed_at"] is not None else None,
        questions=questions_from_messages(messages),
        report=parse_report_json(record["report_json"]),
    )


def load_fallback_session_messages(session_id: str, client_id: str) -> list[Message] | None:
    record = fallback_session_record(session_id, client_id)
    if record is None:
        return None
    set_session_cache(session_id, client_id, record["messages"], str(record["created_at"]), str(record["updated_at"]))
    return clone_messages(record["messages"])


def load_fallback_session_detail(session_id: str, client_id: str) -> SessionDetailResponse:
    record = fallback_session_record(session_id, client_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved session could not be found.",
        )
    set_session_cache(session_id, client_id, record["messages"], str(record["created_at"]), str(record["updated_at"]))
    return SessionDetailResponse(
        client_id=client_id,
        session_id=session_id,
        status=str(record["status"]),
        current_step=int(record["current_step"]),
        created_at=str(record["created_at"]),
        updated_at=str(record["updated_at"]),
        completed_at=str(record["completed_at"]) if record["completed_at"] is not None else None,
        messages=clone_messages(record["messages"]),
        report=parse_report_json(record["report_json"]),
    )


def list_fallback_session_history(client_id: str, limit: int = 4) -> list[SessionHistoryItem]:
    matching_records = []
    for session_id, record in FALLBACK_SESSION_STORE.items():
        if str(record["client_id"]) != client_id:
            continue
        matching_records.append((session_id, record))
    matching_records.sort(key=lambda item: str(item[1]["updated_at"]), reverse=True)
    return [build_history_item_from_record(session_id, record) for session_id, record in matching_records[:limit]]


def sync_fallback_record_from_row(row, messages: list[Message]) -> None:
    set_fallback_session_record(
        row["session_id"],
        row["client_id"],
        messages,
        row["current_step"],
        row["status"],
        row["created_at"],
        row["updated_at"],
        row["completed_at"],
        row["report_json"],
    )


def handle_database_failure(error: Exception) -> None:
    disable_database(error)
    logger.warning("Serving persistence data from in-memory fallback store.")


def load_session_messages(session_id: str, client_id: str) -> list[Message] | None:
    evict_stale_cache_entries()
    cached_messages = get_cached_session_messages(session_id, client_id)
    if cached_messages is not None:
        return cached_messages
    if not database_available():
        return load_fallback_session_messages(session_id, client_id)
    try:
        with get_connection() as connection:
            session_row = fetch_session_row(connection, session_id)
            if session_row is None:
                return None
            ensure_session_owner(session_row["client_id"], client_id)
            message_rows = connection.execute(
                """
                SELECT role, content
                FROM session_messages
                WHERE session_id = ?
                ORDER BY position
                """,
                (session_id,),
            ).fetchall()
    except Exception as error:
        handle_database_failure(error)
        return load_fallback_session_messages(session_id, client_id)
    messages = [Message(role=row["role"], content=row["content"]) for row in message_rows]
    set_session_cache(session_id, client_id, messages, session_row["created_at"], session_row["updated_at"])
    sync_fallback_record_from_row(session_row, messages)
    return clone_messages(messages)


def fetch_session_row(connection, session_id: str):
    return connection.execute(
        """
        SELECT session_id, client_id, status, current_step, created_at, updated_at, completed_at, report_json
        FROM session_records
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()


def ensure_session_exists(session_id: str, client_id: str, current_step: int) -> None:
    existing_messages = load_session_messages(session_id, client_id)
    if existing_messages is not None:
        return
    persist_session_snapshot(session_id, client_id, [], current_step, "in_progress")


def persist_session_snapshot(
    session_id: str,
    client_id: str,
    messages: list[Message],
    current_step: int,
    status_value: str,
    report_payload: dict | None = None,
) -> None:
    evict_stale_cache_entries()
    updated_at = utc_now().isoformat()
    report_json = json.dumps(report_payload) if report_payload else None
    created_at, completed_at = fallback_session_timestamps(session_id, status_value)
    if database_available():
        try:
            with get_connection() as connection:
                created_at, completed_at = session_timestamps(connection, session_id, client_id, status_value)
                upsert_session_row(
                    connection,
                    session_id,
                    client_id,
                    status_value,
                    current_step,
                    created_at,
                    updated_at,
                    completed_at,
                    report_json,
                )
                replace_session_messages(connection, session_id, messages, updated_at)
        except Exception as error:
            handle_database_failure(error)
            created_at, completed_at = fallback_session_timestamps(session_id, status_value)
    set_fallback_session_record(
        session_id,
        client_id,
        messages,
        current_step,
        status_value,
        created_at,
        updated_at,
        completed_at,
        report_json,
    )
    set_session_cache(session_id, client_id, messages, created_at, updated_at)
    invalidate_history_cache(client_id)


def session_timestamps(connection, session_id: str, client_id: str, status_value: str) -> tuple[str, str | None]:
    created_at = utc_now().isoformat()
    completed_at = utc_now().isoformat() if status_value == "complete" else None
    session_row = connection.execute(
        """
        SELECT client_id, created_at, completed_at
        FROM session_records
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if session_row is None:
        return created_at, completed_at
    ensure_session_owner(session_row["client_id"], client_id)
    preserved_completion = session_row["completed_at"] if status_value == "complete" else None
    return session_row["created_at"], preserved_completion or completed_at


def upsert_session_row(
    connection,
    session_id: str,
    client_id: str,
    status_value: str,
    current_step: int,
    created_at: str,
    updated_at: str,
    completed_at: str | None,
    report_json: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO session_records (
            session_id, client_id, status, current_step, created_at, updated_at, completed_at, report_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            client_id = excluded.client_id,
            status = excluded.status,
            current_step = excluded.current_step,
            updated_at = excluded.updated_at,
            completed_at = excluded.completed_at,
            report_json = COALESCE(excluded.report_json, session_records.report_json)
        """,
        (session_id, client_id, status_value, current_step, created_at, updated_at, completed_at, report_json),
    )


def replace_session_messages(connection, session_id: str, messages: list[Message], timestamp: str) -> None:
    connection.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
    connection.executemany(
        """
        INSERT INTO session_messages (session_id, position, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(session_id, index, message.role, message.content, timestamp) for index, message in enumerate(messages)],
    )


def list_session_history(client_id: str, limit: int = 4) -> list[SessionHistoryItem]:
    evict_stale_cache_entries()
    cached_history = HISTORY_CACHE.get(client_id)
    if cached_history is not None:
        cached_history["updated_at"] = utc_now()
        return deepcopy(cached_history["sessions"])
    if not database_available():
        history_items = list_fallback_session_history(client_id, limit)
        HISTORY_CACHE[client_id] = {"sessions": history_items, "updated_at": utc_now()}
        return deepcopy(history_items)
    try:
        with get_connection() as connection:
            session_rows = connection.execute(
                """
                SELECT session_id, client_id, status, current_step, created_at, updated_at, completed_at, report_json
                FROM session_records
                WHERE client_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (client_id, limit),
            ).fetchall()
            messages_by_session = fetch_messages_by_session(connection, [row["session_id"] for row in session_rows])
    except Exception as error:
        handle_database_failure(error)
        history_items = list_fallback_session_history(client_id, limit)
        HISTORY_CACHE[client_id] = {"sessions": history_items, "updated_at": utc_now()}
        return deepcopy(history_items)
    history_items = []
    for row in session_rows:
        messages = messages_by_session.get(row["session_id"], [])
        sync_fallback_record_from_row(row, messages)
        history_items.append(build_history_item_from_record(row["session_id"], FALLBACK_SESSION_STORE[row["session_id"]]))
    HISTORY_CACHE[client_id] = {"sessions": history_items, "updated_at": utc_now()}
    return deepcopy(history_items)


def load_session_detail(session_id: str, client_id: str) -> SessionDetailResponse:
    evict_stale_cache_entries()
    if not database_available():
        return load_fallback_session_detail(session_id, client_id)
    try:
        with get_connection() as connection:
            session_row = fetch_session_row(connection, session_id)
            if session_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Saved session could not be found.",
                )
            ensure_session_owner(session_row["client_id"], client_id)
            message_rows = connection.execute(
                """
                SELECT role, content
                FROM session_messages
                WHERE session_id = ?
                ORDER BY position
                """,
                (session_id,),
            ).fetchall()
    except HTTPException:
        raise
    except Exception as error:
        handle_database_failure(error)
        return load_fallback_session_detail(session_id, client_id)
    messages = [Message(role=row["role"], content=row["content"]) for row in message_rows]
    set_session_cache(session_id, client_id, messages, session_row["created_at"], session_row["updated_at"])
    sync_fallback_record_from_row(session_row, messages)
    return SessionDetailResponse(
        client_id=client_id,
        session_id=session_row["session_id"],
        status=session_row["status"],
        current_step=session_row["current_step"],
        created_at=session_row["created_at"],
        updated_at=session_row["updated_at"],
        completed_at=session_row["completed_at"],
        messages=messages,
        report=parse_report_json(session_row["report_json"]),
    )


def delete_session_history(session_id: str, client_id: str) -> None:
    evict_stale_cache_entries()
    deleted = False
    if database_available():
        try:
            with get_connection() as connection:
                session_row = fetch_session_row(connection, session_id)
                if session_row is not None:
                    ensure_session_owner(session_row["client_id"], client_id)
                    connection.execute("DELETE FROM session_records WHERE session_id = ?", (session_id,))
                    deleted = True
        except HTTPException:
            raise
        except Exception as error:
            handle_database_failure(error)
    fallback_record = fallback_session_record(session_id, client_id)
    if fallback_record is not None:
        deleted = True
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved session could not be found.",
        )
    discard_session_from_memory(session_id)
    invalidate_history_cache(client_id)


def delete_all_session_history(client_id: str) -> int:
    evict_stale_cache_entries()
    deleted_session_ids = set(fallback_session_ids_for_client(client_id))
    if database_available():
        try:
            with get_connection() as connection:
                session_rows = connection.execute(
                    """
                    SELECT session_id
                    FROM session_records
                    WHERE client_id = ?
                    """,
                    (client_id,),
                ).fetchall()
                deleted_session_ids.update(row["session_id"] for row in session_rows)
                connection.execute("DELETE FROM session_records WHERE client_id = ?", (client_id,))
        except Exception as error:
            handle_database_failure(error)
    discard_sessions_from_memory(list(deleted_session_ids))
    invalidate_history_cache(client_id)
    return len(deleted_session_ids)


def fetch_messages_by_session(connection, session_ids: list[str]) -> dict[str, list[Message]]:
    if not session_ids:
        return {}
    placeholders = ",".join("?" for _ in session_ids)
    rows = connection.execute(
        f"""
        SELECT session_id, role, content
        FROM session_messages
        WHERE session_id IN ({placeholders})
        ORDER BY session_id, position
        """,
        session_ids,
    ).fetchall()
    messages_by_session: dict[str, list[Message]] = {session_id: [] for session_id in session_ids}
    for row in rows:
        messages_by_session[row["session_id"]].append(Message(role=row["role"], content=row["content"]))
    return messages_by_session


def parse_report_json(report_json: str | None) -> ReportResponse | None:
    if not report_json:
        return None
    return ReportResponse.model_validate(json.loads(report_json))
