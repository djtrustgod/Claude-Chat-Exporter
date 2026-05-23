"""Domain models for parsed Claude conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Union


Sender = Literal["human", "assistant", "system", "tool"]


@dataclass
class TextPart:
    markdown: str
    kind: Literal["text"] = "text"


@dataclass
class ImagePart:
    file_uuid: str | None
    filename: str | None
    mime: str | None
    source_path: Path | None
    alt: str = ""
    kind: Literal["image"] = "image"


@dataclass
class ToolUsePart:
    name: str
    raw_input: str
    kind: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultPart:
    output: str
    kind: Literal["tool_result"] = "tool_result"


ContentPart = Union[TextPart, ImagePart, ToolUsePart, ToolResultPart]


@dataclass
class Attachment:
    file_uuid: str | None
    filename: str
    mime: str | None = None
    source_path: Path | None = None
    extracted_text: str | None = None
    size_bytes: int | None = None


@dataclass
class Message:
    uuid: str
    sender: Sender
    created_at: datetime | None
    parts: list[ContentPart] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class Chat:
    uuid: str
    name: str
    created_at: datetime | None
    updated_at: datetime | None
    model: str | None
    messages: list[Message] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or "(untitled)"
