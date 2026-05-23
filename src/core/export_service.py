"""High-level export orchestrator used by the GUI.

Takes a Chat + a chosen format and produces a final ZIP. Handles asset
staging in a temp directory and cleanup. Exposes a single function so the
GUI can call it from a worker thread without coupling to exporter internals.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..exporters.base import AssetStager
from ..exporters.docx_exporter import DocxExporter
from ..exporters.markdown_exporter import MarkdownExporter
from ..exporters.pdf_exporter import PdfExporter
from ..packaging.zipper import build_zip
from .assets import build_file_index, resolve_chat_assets
from .models import Chat


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"

    @property
    def label(self) -> str:
        return {
            OutputFormat.MARKDOWN: "Markdown (.md)",
            OutputFormat.DOCX: "Word (.docx)",
            OutputFormat.PDF: "PDF",
        }[self]


_EXPORTERS = {
    OutputFormat.MARKDOWN: MarkdownExporter,
    OutputFormat.DOCX: DocxExporter,
    OutputFormat.PDF: PdfExporter,
}


@dataclass
class ChatExportOutcome:
    chat_uuid: str
    chat_name: str
    zip_path: Path
    missing_count: int
    resolved_count: int


def export_chat(
    chat: Chat,
    fmt: OutputFormat,
    output_dir: Path,
    export_root: Path | None,
) -> ChatExportOutcome:
    """Render ``chat`` to ``fmt`` and return the produced ZIP path.

    ``export_root`` is the directory containing ``conversations.json`` —
    used to locate attachment binaries. If ``None``, no asset resolution
    is attempted; missing attachments are flagged in ``MISSING.txt``.
    """
    file_index = build_file_index(export_root) if export_root else {}
    resolved, missing = resolve_chat_assets(chat, file_index)

    exporter_cls = _EXPORTERS[fmt]
    exporter = exporter_cls()

    with tempfile.TemporaryDirectory(prefix="claude-export-") as tmpdir:
        work_dir = Path(tmpdir)
        stager = AssetStager(work_dir=work_dir)
        stager.stage_chat(chat)
        result = exporter.export(chat, work_dir, stager)

        zip_path = build_zip(
            output_dir=output_dir,
            slug=result.slug,
            doc_path=result.doc_path,
            attachments_dir=result.attachments_dir if result.attachments_dir.exists() else None,
            archive_date=chat.updated_at or chat.created_at,
        )

    return ChatExportOutcome(
        chat_uuid=chat.uuid,
        chat_name=chat.display_name,
        zip_path=zip_path,
        missing_count=missing,
        resolved_count=resolved,
    )
