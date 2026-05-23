"""Resolve attachment/image binaries inside a Claude.ai data export folder."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import Attachment, Chat, ImagePart, Message


_CANDIDATE_SUBDIRS = ("", "attachments", "files", "assets", "images")


def build_file_index(export_root: Path) -> dict[str, Path]:
    """Walk likely subfolders of ``export_root`` and build {key: path}.

    Each binary is indexed by lowercase filename AND by file_uuid if the
    filename looks like ``<uuid>__name.ext`` or starts with a uuid-ish prefix.
    """
    index: dict[str, Path] = {}
    export_root = Path(export_root)
    if not export_root.exists():
        return index

    for sub in _CANDIDATE_SUBDIRS:
        d = export_root / sub if sub else export_root
        if not d.is_dir():
            continue
        for path in d.rglob("*"):
            if not path.is_file() or path.suffix.lower() == ".json":
                continue
            name = path.name.lower()
            index.setdefault(name, path)
            # Common pattern: "<uuid>__<original-name>" or "<uuid>-<name>"
            stem_first = path.stem.split("__", 1)[0].split("-", 1)[0]
            if len(stem_first) >= 8:
                index.setdefault(stem_first.lower(), path)
    return index


def resolve_chat_assets(chat: Chat, file_index: dict[str, Path]) -> tuple[int, int]:
    """Populate ``source_path`` on image parts and attachments for one chat.

    Returns ``(resolved, missing)`` counts.
    """
    resolved = 0
    missing = 0
    for msg in chat.messages:
        for part in msg.parts:
            if isinstance(part, ImagePart):
                path = _lookup(part.filename, part.file_uuid, file_index)
                if path is not None:
                    part.source_path = path
                    resolved += 1
                else:
                    missing += 1
        for att in msg.attachments:
            path = _lookup(att.filename, att.file_uuid, file_index)
            if path is not None:
                att.source_path = path
                resolved += 1
            elif att.extracted_text:
                # Text was extracted by the export — we'll synthesize a file later.
                resolved += 1
            else:
                missing += 1
    return resolved, missing


def iter_message_assets(messages: Iterable[Message]):
    """Yield (kind, obj) tuples for every image/attachment in a chat."""
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ImagePart):
                yield "image", part
        for att in msg.attachments:
            yield "attachment", att


def _lookup(
    filename: str | None,
    file_uuid: str | None,
    index: dict[str, Path],
) -> Path | None:
    if filename:
        hit = index.get(filename.lower())
        if hit is not None:
            return hit
    if file_uuid:
        hit = index.get(file_uuid.lower())
        if hit is not None:
            return hit
    return None
