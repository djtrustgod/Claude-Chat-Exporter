"""Render a Chat to Markdown.

Each message becomes a section. Text parts pass through verbatim; image and
attachment parts are rewritten to point to ``attachments/<file>`` relative
links. The result is human-readable, version-controllable, and re-renderable
by any markdown engine.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import (
    Attachment,
    Chat,
    ContentPart,
    ImagePart,
    Message,
    TextPart,
    ToolResultPart,
    ToolUsePart,
)
from .base import (
    AssetStager,
    ExportResult,
    Exporter,
    format_timestamp,
    role_label,
    safe_slug,
)


class MarkdownExporter(Exporter):
    extension = "md"

    def export(self, chat: Chat, work_dir: Path, stager: AssetStager) -> ExportResult:
        slug = safe_slug(chat.display_name)
        doc_path = work_dir / f"{slug}.md"

        lines: list[str] = []
        lines.extend(self._header(chat))
        for msg in chat.messages:
            lines.extend(self._render_message(msg, stager))
        doc_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

        return ExportResult(
            work_dir=work_dir,
            doc_path=doc_path,
            attachments_dir=stager.attachments_dir,
            slug=slug,
        )

    # ------------------------------------------------------------------
    def _header(self, chat: Chat) -> list[str]:
        out = [f"# {chat.display_name}", ""]
        meta = []
        if chat.created_at:
            meta.append(f"**Created:** {chat.created_at.isoformat()}")
        if chat.updated_at:
            meta.append(f"**Updated:** {chat.updated_at.isoformat()}")
        if chat.model:
            meta.append(f"**Model:** {chat.model}")
        if chat.uuid:
            meta.append(f"**Conversation ID:** `{chat.uuid}`")
        if meta:
            out.append("  \n".join(meta))
            out.append("")
        out.append("---")
        out.append("")
        return out

    def _render_message(self, msg: Message, stager: AssetStager) -> list[str]:
        out: list[str] = []
        ts = format_timestamp(msg)
        header = f"## {role_label(msg)}"
        if ts:
            header += f"  \n_{ts}_"
        out.append(header)
        out.append("")

        for part in msg.parts:
            out.extend(self._render_part(part, stager))
            out.append("")

        if msg.attachments:
            out.extend(self._render_attachments(msg.attachments, stager))
            out.append("")

        out.append("---")
        out.append("")
        return out

    def _render_part(self, part: ContentPart, stager: AssetStager) -> list[str]:
        if isinstance(part, TextPart):
            return [part.markdown.rstrip()]

        if isinstance(part, ImagePart):
            staged = stager.lookup_image(part)
            if staged is None:
                label = part.filename or "image"
                return [f"_[Missing image: {label}]_"]
            alt = staged.alt or part.filename or "image"
            return [f"![{alt}]({staged.rel_path})"]

        if isinstance(part, ToolUsePart):
            return [
                f"**Tool call: `{part.name}`**",
                "",
                "```json",
                part.raw_input.rstrip(),
                "```",
            ]

        if isinstance(part, ToolResultPart):
            quoted = "\n".join(
                f"> {line}" if line else ">"
                for line in part.output.splitlines()
            )
            return ["**Tool result:**", "", quoted]

        return []

    def _render_attachments(
        self, attachments: list[Attachment], stager: AssetStager
    ) -> list[str]:
        lines: list[str] = ["**Attachments:**", ""]
        for att in attachments:
            staged = stager.lookup_attachment(att)
            if staged is None:
                lines.append(f"- {att.filename} _(missing)_")
            else:
                lines.append(f"- [{att.filename}]({staged.rel_path})")
        return lines
