import asyncio
import json
import logging
import os

import httpx

from .models import Message, ReportResponse, StressProfile
from .prompts import (
    build_report_retry_prompt,
    build_report_system_prompt,
    build_report_user_prompt,
)

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.2-chat-latest"
MAX_RETRIES = 3
ASCII_REPLACEMENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
)


def looks_like_openai_key(value: str) -> bool:
    return value.startswith("sk-")


def resolve_openai_api_key() -> str:
    configured_key = (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("OPENAI_APIKEY", "").strip()
        or os.getenv("OPENAI_KEY", "").strip()
    )
    if configured_key:
        return configured_key
    model_value = os.getenv("OPENAI_MODEL", "").strip()
    if looks_like_openai_key(model_value):
        logger.warning("OPENAI_MODEL contains an API key-like value; using it as OPENAI_API_KEY.")
        return model_value
    return ""


def resolve_openai_model() -> str:
    configured_model = os.getenv("OPENAI_MODEL", "").strip()
    if configured_model and not looks_like_openai_key(configured_model):
        return configured_model
    return DEFAULT_MODEL


def normalize_plain_text(value: str) -> str:
    normalized = value.translate(ASCII_REPLACEMENTS)
    return "".join(character for character in normalized if character == "\n" or character == "\t" or ord(character) < 128)


def normalize_report_payload(payload: dict) -> dict:
    profile = payload.get("profile", {})
    actions = payload.get("actions", [])
    return {
        "complete": True,
        "profile": {
            "stress_style": normalize_plain_text(str(profile.get("stress_style", ""))),
            "primary_stressor": normalize_plain_text(str(profile.get("primary_stressor", ""))),
            "body_signals": normalize_plain_text(str(profile.get("body_signals", ""))),
            "coping_pattern": normalize_plain_text(str(profile.get("coping_pattern", ""))),
            "support_need": normalize_plain_text(str(profile.get("support_need", ""))),
        },
        "actions": [normalize_plain_text(str(action)) for action in actions],
    }


class OpenAIGateway:
    def __init__(self) -> None:
        self.api_key = resolve_openai_api_key()
        self.model = resolve_openai_model()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(40.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def stream_chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        fallback_text: str,
    ):
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not set; using fallback chat response.")
            yield fallback_text
            return
        payload = {
            "model": self.model,
            "messages": self._build_messages(system_prompt, messages),
            "stream": True,
        }
        try:
            async for text_chunk in self._stream_with_retries(payload):
                cleaned_chunk = normalize_plain_text(text_chunk or "")
                if cleaned_chunk:
                    yield cleaned_chunk
        except RuntimeError as error:
            logger.error("OpenAI chat stream failed after retries: %s", error)
            yield fallback_text

    async def generate_report(self, transcript: str, messages: list[Message]) -> dict:
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not set; using fallback report.")
            return self._fallback_report(messages).model_dump()
        try:
            response_text = await self._request_report_text(
                build_report_system_prompt(),
                build_report_user_prompt(transcript),
            )
        except RuntimeError as error:
            logger.error("OpenAI report request failed after retries: %s", error)
            return self._fallback_report(messages).model_dump()
        parsed_report = self._parse_report(response_text)
        if parsed_report is not None:
            return normalize_report_payload(parsed_report.model_dump())
        logger.warning("OpenAI returned malformed report JSON; retrying once.")
        try:
            retry_text = await self._request_report_text(
                build_report_system_prompt(),
                build_report_retry_prompt(transcript, response_text),
            )
        except RuntimeError as error:
            logger.error("OpenAI report retry failed after retries: %s", error)
            return self._fallback_report(messages).model_dump()
        retry_report = self._parse_report(retry_text)
        if retry_report is not None:
            return normalize_report_payload(retry_report.model_dump())
        logger.error("OpenAI report JSON was malformed after retry.")
        return self._fallback_report(messages).model_dump()

    async def aclose(self) -> None:
        await self.client.aclose()

    def _build_messages(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return [{"role": "developer", "content": system_prompt}, *messages]

    async def _request_report_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": self._build_messages(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
            ),
        }
        response_json = await self._post_with_retries(payload)
        return self._extract_text_from_response(response_json)

    async def _stream_with_retries(self, payload: dict):
        for attempt in range(MAX_RETRIES):
            try:
                async for text_chunk in self._stream_once(payload):
                    yield text_chunk
                return
            except (httpx.HTTPError, RuntimeError, ValueError) as error:
                logger.warning("OpenAI stream attempt %s failed: %s", attempt + 1, error)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError("stream circuit break") from error
                await asyncio.sleep(2**attempt)

    async def _stream_once(self, payload: dict):
        async with self.client.stream(
            "POST",
            OPENAI_API_URL,
            headers=self._headers(),
            json=payload,
        ) as response:
            response.raise_for_status()
            pending_lines: list[str] = []
            async for line in response.aiter_lines():
                if line:
                    pending_lines.append(line)
                    continue
                text_chunk = self._parse_stream_event(pending_lines)
                pending_lines.clear()
                if text_chunk is not None:
                    yield text_chunk
            trailing_text = self._parse_stream_event(pending_lines)
            if trailing_text is not None:
                yield trailing_text

    def _parse_stream_event(self, lines: list[str]) -> str | None:
        if not lines:
            return None
        data_parts = [line[5:].strip() for line in lines if line.startswith("data:")]
        payload_text = "".join(part for part in data_parts if part != "[DONE]")
        if not payload_text:
            return None
        payload = json.loads(payload_text)
        if "error" in payload:
            message = payload["error"].get("message", "Unknown OpenAI error")
            raise RuntimeError(message)
        choices = payload.get("choices", [])
        if not choices:
            return None
        delta = choices[0].get("delta", {})
        return delta.get("content")

    async def _post_with_retries(self, payload: dict) -> dict:
        for attempt in range(MAX_RETRIES):
            try:
                return await self._post_once(payload)
            except (httpx.HTTPError, ValueError) as error:
                logger.warning("OpenAI request attempt %s failed: %s", attempt + 1, error)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError("request circuit break") from error
                await asyncio.sleep(2**attempt)
        raise RuntimeError("request circuit break")

    async def _post_once(self, payload: dict) -> dict:
        response = await self.client.post(
            OPENAI_API_URL,
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def _extract_text_from_response(self, response_json: dict) -> str:
        choices = response_json.get("choices", [])
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, str):
            return normalize_plain_text(content.strip())
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return normalize_plain_text("".join(text_parts).strip())
        return ""

    def _parse_report(self, response_text: str) -> ReportResponse | None:
        cleaned_text = response_text.strip().removeprefix("```json").removeprefix("```")
        cleaned_text = cleaned_text.removesuffix("```").strip()
        start_index = cleaned_text.find("{")
        end_index = cleaned_text.rfind("}")
        if start_index == -1 or end_index == -1:
            return None
        try:
            payload = json.loads(cleaned_text[start_index : end_index + 1])
        except json.JSONDecodeError:
            return None
        try:
            return ReportResponse.model_validate(payload)
        except Exception as error:
            logger.warning("Report schema validation failed: %s", error)
            return None

    def _fallback_report(self, messages: list[Message]) -> ReportResponse:
        user_responses = [message.content for message in messages if message.role == "user"]
        padded_responses = user_responses + [""] * max(0, 5 - len(user_responses))
        return ReportResponse(
            profile=StressProfile(
                stress_style=self._compact_phrase(padded_responses[0], "heightened and stretched"),
                primary_stressor=self._compact_phrase(padded_responses[1], "multiple demands at once"),
                body_signals=self._compact_phrase(padded_responses[2], "stress showing up in the body"),
                coping_pattern=self._compact_phrase(padded_responses[3], "pushing through where possible"),
                support_need=self._compact_phrase(padded_responses[4], "steady practical support"),
            ),
            actions=[
                "Take two slow minutes to breathe and name the most urgent feeling out loud.",
                "Pick one small next step that would make today feel 10% lighter.",
                "Reach for the kind of support you named instead of waiting until stress spikes.",
            ],
        )

    def _compact_phrase(self, value: str, fallback: str) -> str:
        cleaned_value = normalize_plain_text(" ".join(value.strip().split()))
        if not cleaned_value:
            return fallback
        shortened = cleaned_value[:90].rstrip(" ,.;:")
        return shortened or fallback
