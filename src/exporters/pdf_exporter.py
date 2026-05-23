"""Render a Chat to a PDF using ReportLab."""

from __future__ import annotations

import html
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..core import markdown_walker as mdw
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


_PAGE_W, _PAGE_H = LETTER
_LEFT_MARGIN = 0.9 * inch
_RIGHT_MARGIN = 0.9 * inch
_USABLE_WIDTH = _PAGE_W - _LEFT_MARGIN - _RIGHT_MARGIN
_MAX_IMAGE_WIDTH = min(_USABLE_WIDTH, 5.5 * inch)


class PdfExporter(Exporter):
    extension = "pdf"

    def export(self, chat: Chat, work_dir: Path, stager: AssetStager) -> ExportResult:
        slug = safe_slug(chat.display_name)
        doc_path = work_dir / f"{slug}.pdf"

        styles = _build_styles()
        story: list = []
        story.extend(self._header(chat, styles))
        for msg in chat.messages:
            story.extend(self._render_message(msg, stager, styles))

        doc = SimpleDocTemplate(
            str(doc_path),
            pagesize=LETTER,
            leftMargin=_LEFT_MARGIN,
            rightMargin=_RIGHT_MARGIN,
            topMargin=0.9 * inch,
            bottomMargin=0.9 * inch,
            title=chat.display_name,
        )
        doc.build(story)
        return ExportResult(
            work_dir=work_dir,
            doc_path=doc_path,
            attachments_dir=stager.attachments_dir,
            slug=slug,
        )

    # ------------------------------------------------------------------
    def _header(self, chat: Chat, styles: dict[str, ParagraphStyle]) -> list:
        out = [Paragraph(html.escape(chat.display_name), styles["Title"])]
        meta_lines = []
        if chat.created_at:
            meta_lines.append(f"<b>Created:</b> {html.escape(chat.created_at.isoformat())}")
        if chat.updated_at:
            meta_lines.append(f"<b>Updated:</b> {html.escape(chat.updated_at.isoformat())}")
        if chat.model:
            meta_lines.append(f"<b>Model:</b> {html.escape(chat.model)}")
        if chat.uuid:
            meta_lines.append(f"<b>ID:</b> {html.escape(chat.uuid)}")
        if meta_lines:
            out.append(Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(meta_lines), styles["Meta"]))
        out.append(Spacer(1, 0.15 * inch))
        out.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc")))
        out.append(Spacer(1, 0.1 * inch))
        return out

    def _render_message(
        self,
        msg: Message,
        stager: AssetStager,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        out: list = []
        header_style_key = "HumanHeader" if msg.sender == "human" else (
            "AssistantHeader" if msg.sender == "assistant" else "ToolHeader"
        )
        header = role_label(msg)
        ts = format_timestamp(msg)
        if ts:
            header += f"  <font size='8' color='#777777'><i>·  {html.escape(ts)}</i></font>"
        out.append(Spacer(1, 0.1 * inch))
        out.append(Paragraph(header, styles[header_style_key]))

        for part in msg.parts:
            out.extend(self._render_part(part, stager, styles))

        if msg.attachments:
            out.extend(self._render_attachments(msg.attachments, stager, styles))

        out.append(Spacer(1, 0.06 * inch))
        out.append(HRFlowable(width="100%", color=colors.HexColor("#eeeeee")))
        return out

    # ------------------------------------------------------------------
    def _render_part(
        self,
        part: ContentPart,
        stager: AssetStager,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        if isinstance(part, TextPart):
            return self._render_markdown(part.markdown, stager, styles)

        if isinstance(part, ImagePart):
            return self._render_image_part(part, stager, styles)

        if isinstance(part, ToolUsePart):
            return [
                Paragraph(f"<b>Tool call: {html.escape(part.name)}</b>", styles["Meta"]),
                Preformatted(part.raw_input, styles["Code"]),
                Spacer(1, 0.05 * inch),
            ]

        if isinstance(part, ToolResultPart):
            return [
                Paragraph("<b>Tool result</b>", styles["Meta"]),
                Paragraph(_html_escape_keep_newlines(part.output), styles["Quote"]),
                Spacer(1, 0.05 * inch),
            ]

        return []

    def _render_image_part(
        self,
        part: ImagePart,
        stager: AssetStager,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        staged = stager.lookup_image(part)
        if staged is None:
            return [Paragraph(
                f"<i>[Missing image: {html.escape(part.filename or 'image')}]</i>",
                styles["Missing"],
            )]
        try:
            img = _make_image(staged.abs_path)
        except Exception:  # noqa: BLE001
            return [Paragraph(
                f"<i>[Could not embed image: {html.escape(staged.abs_path.name)}]</i>",
                styles["Missing"],
            )]
        items = [img]
        if staged.alt:
            items.append(Paragraph(
                f"<i>{html.escape(staged.alt)}</i>", styles["Caption"]
            ))
        items.append(Spacer(1, 0.05 * inch))
        return [KeepTogether(items)]

    # ------------------------------------------------------------------
    # Markdown → flowables
    # ------------------------------------------------------------------
    def _render_markdown(
        self,
        markdown_text: str,
        stager: AssetStager,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        renderer = _PdfRenderer(styles)
        for ev in mdw.walk(markdown_text):
            renderer.handle(ev)
        return renderer.finish()

    def _render_attachments(
        self,
        attachments: list[Attachment],
        stager: AssetStager,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        out = [Paragraph("<b>Attachments</b>", styles["Meta"])]
        items = []
        for att in attachments:
            staged = stager.lookup_attachment(att)
            label = html.escape(att.filename)
            if staged is None:
                items.append(ListItem(
                    Paragraph(
                        f'<font color="#993333"><i>{label} (missing)</i></font>',
                        styles["Body"],
                    )
                ))
            else:
                href = html.escape(staged.rel_path)
                items.append(ListItem(
                    Paragraph(
                        f'<link href="{href}" color="#0563C1">{label}</link>'
                        f' &nbsp;<font size="8" color="#777777">→ {href}</font>',
                        styles["Body"],
                    )
                ))
        out.append(ListFlowable(items, bulletType="bullet", start="circle"))
        return out


# ----------------------------------------------------------------------
# PDF renderer state machine
# ----------------------------------------------------------------------
class _PdfRenderer:
    def __init__(self, styles: dict[str, ParagraphStyle]):
        self.styles = styles
        self.flowables: list = []
        self._buf: list[str] = []   # accumulating inline html for current paragraph
        self._block_style: ParagraphStyle | None = None
        # Lists
        self._list_stack: list[dict] = []  # each: {"ordered": bool, "items": [..]}
        # Tables
        self._table_rows: list[list[str]] = []
        self._table_current_row: list[str] | None = None
        self._table_current_cell: list[str] | None = None
        self._table_section: str | None = None
        self._table_n_header_rows = 0
        self._table_active = False
        # Blockquote
        self._blockquote_depth = 0

    def handle(self, ev) -> None:
        if isinstance(ev, mdw.BlockOpen):
            self._open(ev)
        elif isinstance(ev, mdw.BlockClose):
            self._close(ev)
        elif isinstance(ev, mdw.Run):
            self._add_run(ev)
        elif isinstance(ev, mdw.InlineImage):
            self._buf.append(f"<i>[image: {html.escape(ev.alt or ev.src)}]</i>")
        elif isinstance(ev, mdw.HardBreak):
            self._buf.append("<br/>")

    def finish(self) -> list:
        # Flush dangling paragraph if any
        if self._buf and self._block_style is not None:
            self._emit_paragraph()
        return self.flowables

    # ----- block handling -----
    def _open(self, ev: mdw.BlockOpen) -> None:
        kind = ev.kind
        if kind == "paragraph":
            self._block_style = self._select_style("Body")
        elif kind == "heading":
            key = f"H{min(max(ev.level, 1), 4)}"
            self._block_style = self.styles.get(key, self.styles["Body"])
        elif kind == "code_block":
            # self-closing in our walker
            self._emit_code_block(ev.source, ev.lang)
        elif kind == "list":
            self._list_stack.append({"ordered": ev.ordered, "items": []})
        elif kind == "list_item":
            self._block_style = self._select_style("Body")
        elif kind == "blockquote":
            self._blockquote_depth += 1
        elif kind == "table":
            self._table_active = True
            self._table_rows = []
            self._table_n_header_rows = 0
        elif kind in ("thead", "tbody"):
            self._table_section = kind
        elif kind == "tr":
            self._table_current_row = []
        elif kind in ("th", "td"):
            self._table_current_cell = []
            self._block_style = self._select_style("Body")
        elif kind == "hr":
            self._flush_paragraph_if_any()
            self.flowables.append(Spacer(1, 0.05 * inch))
            self.flowables.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc")))
            self.flowables.append(Spacer(1, 0.05 * inch))

    def _close(self, ev: mdw.BlockClose) -> None:
        kind = ev.kind
        if kind == "paragraph":
            self._emit_paragraph()
        elif kind == "heading":
            self._emit_paragraph()
        elif kind == "list_item":
            text_html = "".join(self._buf).strip()
            self._buf = []
            if self._list_stack:
                self._list_stack[-1]["items"].append(
                    ListItem(Paragraph(text_html or "&nbsp;", self.styles["Body"]))
                )
            self._block_style = None
        elif kind == "list":
            if not self._list_stack:
                return
            data = self._list_stack.pop()
            list_flow = ListFlowable(
                data["items"],
                bulletType="1" if data["ordered"] else "bullet",
                start="1" if data["ordered"] else "circle",
                leftIndent=0.25 * inch * (len(self._list_stack) + 1),
            )
            if self._list_stack:
                # Append nested list as a flowable inside the parent's last item
                parent = self._list_stack[-1]
                if parent["items"]:
                    last = parent["items"][-1]
                    last._flowables = list(last._flowables) + [list_flow]
                else:
                    parent["items"].append(ListItem(list_flow))
            else:
                self.flowables.append(list_flow)
        elif kind == "blockquote":
            self._blockquote_depth = max(0, self._blockquote_depth - 1)
        elif kind == "table":
            self._emit_table()
            self._table_active = False
        elif kind in ("thead", "tbody"):
            self._table_section = None
        elif kind == "tr":
            if self._table_current_row is not None:
                if self._table_section == "thead":
                    self._table_n_header_rows += 1
                self._table_rows.append(self._table_current_row)
            self._table_current_row = None
        elif kind in ("th", "td"):
            text_html = "".join(self._buf).strip()
            self._buf = []
            if self._table_current_row is not None:
                self._table_current_row.append(text_html)
            self._table_current_cell = None
            self._block_style = None

    # ----- inline -----
    def _add_run(self, run_ev: mdw.Run) -> None:
        text = html.escape(run_ev.text).replace("\n", "<br/>")
        if not text:
            return
        if run_ev.code:
            text = f'<font face="Courier" size="9" backColor="#EFEFEF">{text}</font>'
        if run_ev.bold:
            text = f"<b>{text}</b>"
        if run_ev.italic:
            text = f"<i>{text}</i>"
        if run_ev.href:
            text = f'<link href="{html.escape(run_ev.href)}" color="#0563C1">{text}</link>'
        self._buf.append(text)

    # ----- helpers -----
    def _select_style(self, base: str) -> ParagraphStyle:
        if self._blockquote_depth and base == "Body":
            return self.styles["Quote"]
        return self.styles[base]

    def _emit_paragraph(self) -> None:
        text_html = "".join(self._buf).strip()
        self._buf = []
        if not text_html or self._block_style is None:
            self._block_style = None
            return
        self.flowables.append(Paragraph(text_html, self._block_style))
        self._block_style = None

    def _flush_paragraph_if_any(self) -> None:
        if self._buf and self._block_style is not None:
            self._emit_paragraph()

    def _emit_code_block(self, source: str, lang: str) -> None:
        self._flush_paragraph_if_any()
        if lang:
            self.flowables.append(Paragraph(
                f"<font size='8' color='#777777'>{html.escape(lang)}</font>",
                self.styles["Meta"],
            ))
        self.flowables.append(Preformatted(source.rstrip("\n"), self.styles["Code"]))
        self.flowables.append(Spacer(1, 0.04 * inch))

    def _emit_table(self) -> None:
        if not self._table_rows:
            return
        # Normalize to equal columns
        ncols = max(len(r) for r in self._table_rows)
        rows: list[list] = []
        for r in self._table_rows:
            padded = list(r) + ["" for _ in range(ncols - len(r))]
            rows.append([Paragraph(c or "&nbsp;", self.styles["TableCell"]) for c in padded])
        col_widths = [_USABLE_WIDTH / ncols] * ncols
        tbl = Table(rows, colWidths=col_widths, repeatRows=self._table_n_header_rows)
        style_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if self._table_n_header_rows:
            style_cmds.append(("BACKGROUND", (0, 0), (-1, self._table_n_header_rows - 1), colors.HexColor("#f2f2f2")))
            style_cmds.append(("FONTNAME", (0, 0), (-1, self._table_n_header_rows - 1), "Helvetica-Bold"))
        tbl.setStyle(TableStyle(style_cmds))
        self.flowables.append(tbl)
        self.flowables.append(Spacer(1, 0.05 * inch))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    styles["Title"] = ParagraphStyle(
        "ChatTitle", parent=base["Title"], fontSize=20, leading=24, alignment=TA_LEFT,
        textColor=colors.HexColor("#222222"),
    )
    styles["Meta"] = ParagraphStyle(
        "Meta", parent=base["BodyText"], fontSize=8.5, leading=11,
        textColor=colors.HexColor("#666666"), spaceAfter=4,
    )
    styles["Body"] = ParagraphStyle(
        "Body", parent=base["BodyText"], fontSize=10.5, leading=14,
        spaceBefore=2, spaceAfter=4, textColor=colors.HexColor("#222222"),
    )
    styles["H1"] = ParagraphStyle(
        "H1", parent=base["Heading1"], fontSize=16, leading=20, spaceBefore=10,
        spaceAfter=4, textColor=colors.HexColor("#1a1a1a"),
    )
    styles["H2"] = ParagraphStyle(
        "H2", parent=base["Heading2"], fontSize=13.5, leading=17, spaceBefore=8,
        spaceAfter=3, textColor=colors.HexColor("#1a1a1a"),
    )
    styles["H3"] = ParagraphStyle(
        "H3", parent=base["Heading3"], fontSize=12, leading=15, spaceBefore=6,
        spaceAfter=2, textColor=colors.HexColor("#1a1a1a"),
    )
    styles["H4"] = ParagraphStyle(
        "H4", parent=base["Heading4"], fontSize=11, leading=14, spaceBefore=5,
        spaceAfter=2, textColor=colors.HexColor("#333333"),
    )
    styles["HumanHeader"] = ParagraphStyle(
        "HumanHeader", parent=styles["Body"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, spaceBefore=10, spaceAfter=2,
        textColor=colors.HexColor("#164A84"),
    )
    styles["AssistantHeader"] = ParagraphStyle(
        "AssistantHeader", parent=styles["Body"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, spaceBefore=10, spaceAfter=2,
        textColor=colors.HexColor("#8B330E"),
    )
    styles["ToolHeader"] = ParagraphStyle(
        "ToolHeader", parent=styles["Body"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, spaceBefore=10, spaceAfter=2,
        textColor=colors.HexColor("#555555"),
    )
    styles["Code"] = ParagraphStyle(
        "Code", parent=base["Code"], fontName="Courier", fontSize=9, leading=12,
        leftIndent=8, rightIndent=8, spaceBefore=2, spaceAfter=4,
        textColor=colors.HexColor("#222222"), backColor=colors.HexColor("#f4f4f4"),
        borderColor=colors.HexColor("#dddddd"), borderWidth=0.4, borderPadding=4,
    )
    styles["Quote"] = ParagraphStyle(
        "Quote", parent=styles["Body"], leftIndent=14, textColor=colors.HexColor("#444444"),
        borderColor=colors.HexColor("#888888"), borderWidth=0, spaceBefore=2, spaceAfter=4,
    )
    styles["Caption"] = ParagraphStyle(
        "Caption", parent=styles["Meta"], alignment=1, fontSize=8.5,
    )
    styles["Missing"] = ParagraphStyle(
        "Missing", parent=styles["Body"], textColor=colors.HexColor("#993333"),
    )
    styles["TableCell"] = ParagraphStyle(
        "TableCell", parent=styles["Body"], fontSize=9.5, leading=12,
        spaceBefore=0, spaceAfter=0,
    )
    return styles


def _make_image(path: Path) -> Image:
    with PILImage.open(path) as im:
        w_px, h_px = im.size
    native_w_pts = (w_px / 96.0) * inch
    if native_w_pts > _MAX_IMAGE_WIDTH:
        scale = _MAX_IMAGE_WIDTH / native_w_pts
    else:
        # Don't upscale, just use native size.
        scale = 1.0
    img = Image(str(path))
    img.drawWidth = (w_px / 96.0) * inch * scale
    img.drawHeight = (h_px / 96.0) * inch * scale
    return img


def _html_escape_keep_newlines(text: str) -> str:
    return html.escape(text).replace("\n", "<br/>")
