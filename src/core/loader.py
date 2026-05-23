"""Parse a Claude.ai data export ``conversations.json`` into domain models.

The exporter has shipped multiple schema variants over time. This loader is
intentionally permissive: unknown fields are ignored and unknown content-part
``type`` values are preserved as a text placeholder rather than crashing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    Attachment,
    Chat,
    ContentPart,
    ImagePart,
    Message,
    Sender,
    TextPart,
    ToolResultPart,
    ToolUsePart,
)


def load_export(json_path: Path) -> list[Chat]:
    """Load conversations.json and return a list of Chat objects."""
    json_path = Path(json_path)
    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array at the top level of {json_path.name}, "
            f"got {type(data).__name__}."
        )

    chats: list[Chat] = []
    for raw in data:
        try:
            chats.append(_parse_chat(raw))
        except Exception as exc:  # noqa: BLE001
            uuid = raw.get("uuid", "?") if isinstance(raw, dict) else "?"
            raise ValueError(f"Failed to parse conversation {uuid}: {exc}") from exc

    chats.sort(
        key=lambda c: c.updated_at or c.created_at or datetime.min,
        reverse=True,
    )
    return chats


def _parse_chat(raw: dict[str, Any]) -> Chat:
    msgs_raw = raw.get("chat_messages") or raw.get("messages") or []
    messages = [_parse_message(m) for m in msgs_raw]
    messages = [m for m in messages if _message_has_content(m)]

    return Chat(
        uuid=str(raw.get("uuid") or raw.get("id") or ""),
        name=str(raw.get("name") or raw.get("title") or "").strip(),
        created_at=_parse_dt(raw.get("created_at")),
        updated_at=_parse_dt(raw.get("updated_at")),
        model=raw.get("model") or raw.get("model_slug"),
        messages=messages,
    )


def _parse_message(raw: dict[str, Any]) -> Message:
    sender = _normalize_sender(raw.get("sender") or raw.get("role") or "")
    parts = _parse_parts(raw)
    attachments = [_parse_attachment(a) for a in (raw.get("files") or [])]
    attachments += [_parse_attachment(a) for a in (raw.get("attachments") or [])]
    # Dedupe by (file_uuid, filename)
    seen: set[tuple[str | None, str]] = set()
    unique: list[Attachment] = []
    for a in attachments:
        key = (a.file_uuid, a.filename)
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)

    return Message(
        uuid=str(raw.get("uuid") or raw.get("id") or ""),
        sender=sender,
        created_at=_parse_dt(raw.get("created_at")),
        parts=parts,
        attachments=unique,
    )


def _parse_parts(raw: dict[str, Any]) -> list[ContentPart]:
    parts: list[ContentPart] = []
    content = raw.get("content")

    if isinstance(content, list) and content:
        for item in content:
            part = _parse_content_item(item)
            if part is not None:
                parts.append(part)
    elif isinstance(content, str) and content.strip():
        parts.append(TextPart(markdown=content))

    # Fall back to top-level `text` if no parts were parsed.
    if not parts:
        text = raw.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(TextPart(markdown=text))

    return parts


def _parse_content_item(item: Any) -> ContentPart | None:
    if not isinstance(item, dict):
        return None

    type_ = (item.get("type") or "").lower()

    if type_ in ("text", ""):
        text = item.get("text") or ""
        if not isinstance(text, str):
            text = str(text)
        if not text.strip():
            return None
        return TextPart(markdown=text)

    if type_ in ("image", "image_url", "input_image"):
        # The export sometimes nests under "image" or "image_url" keys.
        src = (
            item.get("source")
            or item.get("image")
            or item.get("image_url")
            or {}
        )
        if isinstance(src, str):
            file_uuid = None
            filename = src.rsplit("/", 1)[-1] if "/" in src else src
            mime = None
        else:
            file_uuid = src.get("file_uuid") or item.get("file_uuid")
            filename = src.get("file_name") or src.get("filename") or item.get("file_name")
            mime = src.get("media_type") or src.get("mime_type") or item.get("media_type")
        return ImagePart(
            file_uuid=file_uuid,
            filename=filename,
            mime=mime,
            source_path=None,
            alt=str(item.get("alt") or ""),
        )

    if type_ in ("tool_use", "tool_call"):
        return ToolUsePart(
            name=str(item.get("name") or "tool"),
            raw_input=json.dumps(item.get("input") or {}, ensure_ascii=False, indent=2),
        )

    if type_ in ("tool_result", "tool_response"):
        out = item.get("content") or item.get("output") or ""
        if isinstance(out, list):
            # Recursively render any nested text parts.
            collected = []
            for sub in out:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    collected.append(str(sub.get("text", "")))
                elif isinstance(sub, str):
                    collected.append(sub)
            out = "\n".join(collected)
        return ToolResultPart(output=str(out))

    # Unknown type: keep something readable.
    return TextPart(markdown=f"_[Unsupported content part: `{type_}`]_")


def _parse_attachment(raw: dict[str, Any]) -> Attachment:
    return Attachment(
        file_uuid=raw.get("file_uuid") or raw.get("uuid") or raw.get("id"),
        filename=str(
            raw.get("file_name")
            or raw.get("filename")
            or raw.get("name")
            or "unnamed-file"
        ),
        mime=raw.get("file_type") or raw.get("media_type") or raw.get("mime_type"),
        source_path=None,
        extracted_text=raw.get("extracted_content") or raw.get("text"),
        size_bytes=raw.get("file_size") or raw.get("size"),
    )


def _normalize_sender(value: str) -> Sender:
    v = value.lower().strip()
    if v in ("human", "user"):
        return "human"
    if v in ("assistant", "ai", "claude"):
        return "assistant"
    if v == "system":
        return "system"
    if v == "tool":
        return "tool"
    return "assistant"  # safe default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    # Normalize trailing Z to +00:00 for fromisoformat
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _message_has_content(msg: Message) -> bool:
    if msg.attachments:
        return True
    for p in msg.parts:
        if isinstance(p, TextPart) and p.markdown.strip():
            return True
        if isinstance(p, (ImagePart, ToolUsePart, ToolResultPart)):
            return True
    return False
