"""Exporter contract + shared asset-staging utilities.

All three exporters (markdown/docx/pdf) follow the same skeleton:

  1. Create a clean work directory.
  2. Stage all images + attachments into ``<workdir>/attachments/``,
     returning a mapping from the original asset to its relative path
     in the document.
  3. Render the document, looking up assets via the mapping.
  4. Return an ``ExportResult`` for the zipper to bundle.
"""

from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..core.models import Attachment, Chat, ImagePart, Message


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_DOC_FRIENDLY_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def safe_slug(name: str, max_len: int = 80) -> str:
    """Convert ``name`` to a filesystem-safe ASCII-ish slug."""
    s = (name or "untitled").strip()
    # Convert to ASCII where possible (keep Unicode letters in mind, but conservative).
    s = s.encode("ascii", errors="ignore").decode("ascii") or "untitled"
    s = _SAFE_FILENAME_RE.sub("-", s).strip("-._") or "untitled"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-._")
    return s or "untitled"


def safe_filename(name: str, max_len: int = 100) -> str:
    """Like ``safe_slug`` but preserves the extension."""
    name = (name or "file").strip()
    name = name.encode("ascii", errors="ignore").decode("ascii") or "file"
    name = name.replace("\\", "_").replace("/", "_")
    name = _SAFE_FILENAME_RE.sub("_", name).strip("._-") or "file"
    if len(name) > max_len:
        stem, _, ext = name.rpartition(".")
        if stem and ext:
            keep = max_len - len(ext) - 1
            name = stem[:keep] + "." + ext
        else:
            name = name[:max_len]
    return name


@dataclass
class StagedImage:
    """An image staged into ``attachments/``. Always doc-friendly format."""
    rel_path: str                  # e.g. "attachments/img-001.png"
    abs_path: Path                 # absolute path on disk inside work dir
    alt: str
    embedded_ok: bool              # whether ``abs_path`` is openable by PIL


@dataclass
class StagedAttachment:
    """A non-embedded attachment (PDF, code file, etc.)."""
    rel_path: str
    abs_path: Path
    filename: str                  # original-ish display name
    mime: str | None


@dataclass
class MissingAsset:
    filename: str
    reason: str


@dataclass
class ExportResult:
    work_dir: Path
    doc_path: Path
    attachments_dir: Path
    slug: str


@dataclass
class AssetStager:
    """Stages images + attachments to ``<work_dir>/attachments/`` with stable names.

    A single instance is shared across one chat export. It tracks used names
    to disambiguate collisions, and accumulates a MissingAsset list to write
    out as ``attachments/MISSING.txt`` at the end.
    """
    work_dir: Path
    attachments_dirname: str = "attachments"
    _used_names: set[str] = field(default_factory=set)
    _image_for_id: dict[str, StagedImage] = field(default_factory=dict)
    _attachment_for_id: dict[str, StagedAttachment] = field(default_factory=dict)
    missing: list[MissingAsset] = field(default_factory=list)
    _image_counter: int = 0

    @property
    def attachments_dir(self) -> Path:
        d = self.work_dir / self.attachments_dirname
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Pre-staging: walk the chat once so the same image referenced twice
    # ends up as a single file on disk.
    # ------------------------------------------------------------------
    def stage_chat(self, chat: Chat) -> None:
        for msg in chat.messages:
            for part in msg.parts:
                if isinstance(part, ImagePart):
                    self.stage_image(part)
            for att in msg.attachments:
                self.stage_attachment(att)
        self._write_missing_file()

    # ------------------------------------------------------------------
    # Image staging
    # ------------------------------------------------------------------
    def stage_image(self, image: ImagePart) -> StagedImage | None:
        key = self._image_key(image)
        if key in self._image_for_id:
            return self._image_for_id[key]

        if image.source_path is None or not image.source_path.exists():
            self.missing.append(
                MissingAsset(
                    filename=image.filename or (image.file_uuid or "image"),
                    reason="image binary not found in export folder",
                )
            )
            return None

        self._image_counter += 1
        base_name = image.filename or f"image-{self._image_counter:03d}"
        dest = self._copy_image(image.source_path, base_name)
        if dest is None:
            self.missing.append(
                MissingAsset(
                    filename=base_name,
                    reason="image format unsupported or unreadable",
                )
            )
            return None

        staged = StagedImage(
            rel_path=f"{self.attachments_dirname}/{dest.name}",
            abs_path=dest,
            alt=image.alt or "",
            embedded_ok=True,
        )
        self._image_for_id[key] = staged
        return staged

    def lookup_image(self, image: ImagePart) -> StagedImage | None:
        return self._image_for_id.get(self._image_key(image))

    # ------------------------------------------------------------------
    # Attachment staging
    # ------------------------------------------------------------------
    def stage_attachment(self, att: Attachment) -> StagedAttachment | None:
        key = self._attachment_key(att)
        if key in self._attachment_for_id:
            return self._attachment_for_id[key]

        # 1) Real file present
        if att.source_path is not None and att.source_path.exists():
            base = att.filename or att.source_path.name
            dest_name = self._unique_filename(safe_filename(base))
            dest = self.attachments_dir / dest_name
            shutil.copy2(att.source_path, dest)
            staged = StagedAttachment(
                rel_path=f"{self.attachments_dirname}/{dest_name}",
                abs_path=dest,
                filename=att.filename,
                mime=att.mime,
            )
            self._attachment_for_id[key] = staged
            return staged

        # 2) No binary but Claude extracted text — synthesize a .txt
        if att.extracted_text:
            base = (att.filename or "extracted") + ".extracted.txt"
            dest_name = self._unique_filename(safe_filename(base))
            dest = self.attachments_dir / dest_name
            header = (
                f"[Extracted text content for: {att.filename}]\n"
                f"[Original binary was not present in the data export.]\n"
                f"{'-' * 60}\n\n"
            )
            dest.write_text(header + att.extracted_text, encoding="utf-8")
            staged = StagedAttachment(
                rel_path=f"{self.attachments_dirname}/{dest_name}",
                abs_path=dest,
                filename=att.filename,
                mime="text/plain",
            )
            self._attachment_for_id[key] = staged
            return staged

        # 3) Nothing — record as missing
        self.missing.append(
            MissingAsset(
                filename=att.filename or (att.file_uuid or "attachment"),
                reason="attachment binary not found and no extracted text",
            )
        )
        return None

    def lookup_attachment(self, att: Attachment) -> StagedAttachment | None:
        return self._attachment_for_id.get(self._attachment_key(att))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _image_key(self, image: ImagePart) -> str:
        return (
            image.file_uuid
            or (str(image.source_path) if image.source_path else None)
            or (image.filename or "")
            or id(image).__str__()
        )

    def _attachment_key(self, att: Attachment) -> str:
        return (
            att.file_uuid
            or (str(att.source_path) if att.source_path else None)
            or att.filename
            or id(att).__str__()
        )

    def _unique_filename(self, name: str) -> str:
        if name not in self._used_names:
            self._used_names.add(name)
            return name
        stem, dot, ext = name.rpartition(".")
        base = stem if dot else name
        suffix = ext if dot else ""
        i = 1
        while True:
            candidate = f"{base}-{i}.{suffix}" if suffix else f"{base}-{i}"
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate
            i += 1

    def _copy_image(self, source: Path, base_name: str) -> Path | None:
        """Copy + convert (if needed) into a doc-friendly format."""
        ext = source.suffix.lower()
        if ext in _DOC_FRIENDLY_IMAGE_EXTS:
            dest_name = self._unique_filename(safe_filename(base_name))
            dest = self.attachments_dir / dest_name
            try:
                shutil.copy2(source, dest)
            except OSError:
                return None
            # Quick PIL verify; if unreadable, treat as missing.
            try:
                with Image.open(dest) as im:
                    im.verify()
            except (UnidentifiedImageError, OSError):
                dest.unlink(missing_ok=True)
                return None
            return dest

        # Convert via PIL to PNG.
        png_name = safe_filename(Path(base_name).stem + ".png")
        dest_name = self._unique_filename(png_name)
        dest = self.attachments_dir / dest_name
        try:
            with Image.open(source) as im:
                im = im.convert("RGBA" if im.mode in ("LA", "RGBA", "P") else "RGB")
                im.save(dest, format="PNG")
        except (UnidentifiedImageError, OSError):
            return None
        return dest

    def _write_missing_file(self) -> None:
        if not self.missing:
            return
        lines = ["# Missing assets", ""]
        lines.append(
            "The following attachments / images were referenced by the "
            "conversation but could not be located inside the data export "
            "folder. Document references to them are preserved so you know "
            "what was there.\n"
        )
        for m in self.missing:
            lines.append(f"- {m.filename} — {m.reason}")
        (self.attachments_dir / "MISSING.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


class Exporter(ABC):
    """Base class for all format exporters."""

    extension: str = ""

    @abstractmethod
    def export(self, chat: Chat, work_dir: Path, stager: AssetStager) -> ExportResult:
        """Render ``chat`` into ``work_dir`` and return an ExportResult."""
        raise NotImplementedError


def role_label(msg: Message) -> str:
    if msg.sender == "human":
        return "Human"
    if msg.sender == "assistant":
        return "Assistant"
    if msg.sender == "tool":
        return "Tool"
    if msg.sender == "system":
        return "System"
    return msg.sender.title() if msg.sender else "Unknown"


def format_timestamp(msg: Message) -> str:
    if msg.created_at is None:
        return ""
    return msg.created_at.strftime("%Y-%m-%d %H:%M")
