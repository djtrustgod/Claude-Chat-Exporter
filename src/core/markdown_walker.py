"""Turn a Markdown string into a stream of format-agnostic render events.

Exporters (markdown/docx/pdf) consume the same event stream and render in
their own way. Markdown is parsed once; rendering logic stays small.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Union

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass
class BlockOpen:
    kind: str  # paragraph|heading|code_block|list|list_item|blockquote|table|thead|tbody|tr|th|td|hr
    level: int = 0  # heading level (1-6)
    ordered: bool = False  # list ordering
    lang: str = ""  # code block language
    source: str = ""  # code block content (only for self-closing code_block)


@dataclass
class BlockClose:
    kind: str


@dataclass
class Run:
    """A run of inline text with optional formatting/link."""
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    href: str | None = None


@dataclass
class InlineImage:
    alt: str
    src: str


@dataclass
class HardBreak:
    pass


Event = Union[BlockOpen, BlockClose, Run, InlineImage, HardBreak]


_md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table").enable("strikethrough")


def walk(markdown_text: str) -> Iterator[Event]:
    """Yield render events for the given markdown string."""
    tokens = _md.parse(markdown_text or "")
    yield from _walk_tokens(tokens)


def _walk_tokens(tokens: list[Token]) -> Iterator[Event]:
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type

        if t == "paragraph_open":
            yield BlockOpen("paragraph")
        elif t == "paragraph_close":
            yield BlockClose("paragraph")
        elif t == "heading_open":
            yield BlockOpen("heading", level=int(tok.tag[1:]))
        elif t == "heading_close":
            yield BlockClose("heading")
        elif t == "bullet_list_open":
            yield BlockOpen("list", ordered=False)
        elif t == "bullet_list_close":
            yield BlockClose("list")
        elif t == "ordered_list_open":
            yield BlockOpen("list", ordered=True)
        elif t == "ordered_list_close":
            yield BlockClose("list")
        elif t == "list_item_open":
            yield BlockOpen("list_item")
        elif t == "list_item_close":
            yield BlockClose("list_item")
        elif t == "blockquote_open":
            yield BlockOpen("blockquote")
        elif t == "blockquote_close":
            yield BlockClose("blockquote")
        elif t == "hr":
            yield BlockOpen("hr")
            yield BlockClose("hr")
        elif t == "fence" or t == "code_block":
            yield BlockOpen("code_block", lang=(tok.info or "").strip(), source=tok.content or "")
            yield BlockClose("code_block")
        elif t == "table_open":
            yield BlockOpen("table")
        elif t == "table_close":
            yield BlockClose("table")
        elif t == "thead_open":
            yield BlockOpen("thead")
        elif t == "thead_close":
            yield BlockClose("thead")
        elif t == "tbody_open":
            yield BlockOpen("tbody")
        elif t == "tbody_close":
            yield BlockClose("tbody")
        elif t == "tr_open":
            yield BlockOpen("tr")
        elif t == "tr_close":
            yield BlockClose("tr")
        elif t == "th_open":
            yield BlockOpen("th")
        elif t == "th_close":
            yield BlockClose("th")
        elif t == "td_open":
            yield BlockOpen("td")
        elif t == "td_close":
            yield BlockClose("td")
        elif t == "inline":
            yield from _walk_inline(tok.children or [])
        elif t == "html_block":
            # Render raw HTML as plaintext paragraph to avoid losing content.
            yield BlockOpen("paragraph")
            yield Run(tok.content.strip())
            yield BlockClose("paragraph")
        # else: ignore unknown tokens silently

        i += 1


def _walk_inline(children: list[Token]) -> Iterator[Event]:
    bold = False
    italic = False
    code = False
    href: str | None = None

    for tok in children:
        t = tok.type
        if t == "text":
            if tok.content:
                yield Run(tok.content, bold=bold, italic=italic, code=code, href=href)
        elif t == "strong_open":
            bold = True
        elif t == "strong_close":
            bold = False
        elif t == "em_open":
            italic = True
        elif t == "em_close":
            italic = False
        elif t == "s_open":
            # Strikethrough — we don't have a separate flag, downgrade to italic.
            italic = True
        elif t == "s_close":
            italic = False
        elif t == "code_inline":
            yield Run(tok.content, bold=bold, italic=italic, code=True, href=href)
        elif t == "link_open":
            href = tok.attrGet("href") or ""
        elif t == "link_close":
            href = None
        elif t == "image":
            alt = tok.content or (tok.attrGet("alt") or "")
            src = tok.attrGet("src") or ""
            yield InlineImage(alt=alt, src=src)
        elif t == "softbreak":
            yield Run(" ", bold=bold, italic=italic, code=code, href=href)
        elif t == "hardbreak":
            yield HardBreak()
        elif t == "html_inline":
            if tok.content:
                yield Run(tok.content, bold=bold, italic=italic, code=code, href=href)
        # ignore unknown inline tokens
