# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Custom app logo (chat bubble + download arrow) drawn from scratch with
  Pillow — see [assets/generate_logo.py](assets/generate_logo.py).
- Logo shown in the GUI header alongside the app name and version.
- Multi-resolution `logo.ico` used as the Windows title-bar / taskbar icon.
- "How to Export" link at the top of the right-hand Export panel — opens an
  in-app help dialog with the full step-by-step workflow and a shortcut to
  Claude.ai's data-privacy settings page.

### Changed
- Logo redesigned with a more pronounced chat-bubble silhouette (smaller
  bubble inside the tile, larger tail) so the speech-bubble shape reads
  clearly at all sizes.
- Separate `logo_light.png` and `logo_dark.png` variants generated and
  wired into `CTkImage(light_image=..., dark_image=...)`. The dark variant
  uses a vivid orange bubble (#FF8C5A) with a warm-white outline on a
  medium-gray tile (#3A3A42) for high contrast against dark window chrome.
- Logo display size in the GUI header bumped from 44×44 to 56×56 px.
- "How to Export" promoted from an underlined text link to a clearly-styled
  blue CTkButton at the top of the Export panel — much more discoverable
  than a label that looked like passive text.
- That button + its help dialog re-titled to "How to Get your Claude Chat
  File" — the previous "Export / How to Export" combo was confusing
  because it lived next to the in-app "Export" controls; the new wording
  makes clear it explains how to obtain the input `conversations.json`
  from Claude.ai, not how to drive this app's exporter.
- Top-bar "Load export…" button renamed to "Load Chat File", and the
  accompanying "Export file:" label renamed to "Chat File:" — consistent
  with "chat file" being the input you load and "export" being what this
  app produces.
- Header logo shrunk from 56×56 → 28×28 so it sits inline alongside the
  "Claude Chat Exporter" title rather than spanning the title + version
  rows.

## [1.0.0] - 2026-05-23

### Added
- Initial CustomTkinter GUI for browsing and exporting chats from a Claude.ai
  data export (`conversations.json`).
- Multi-select chat list with search/filter and bulk-select controls.
- Three output formats:
  - Markdown (`.md`) — readable + version-controllable, renders verbatim.
  - Word (`.docx`) — via `python-docx`, with styled headings, code blocks,
    blockquotes, tables, lists, and inline images.
  - PDF — via `reportlab`, same rich rendering through a shared
    markdown-walker event stream.
- Per-chat ZIP bundling: `<slug>-<date>.zip` containing the document plus
  an `attachments/` subfolder with all referenced images and files.
- Inline images are embedded directly into the document AND copied into
  `attachments/` so both viewing and direct-file access work.
- Non-embeddable attachments (PDFs, code, binaries) are placed in
  `attachments/` and linked from the document via relative paths.
- Robust loader that handles both legacy flat-text and modern
  `content[]`-array conversation schemas; unknown content-part types
  are preserved as placeholders rather than crashing.
- Background export worker keeps the GUI responsive; progress bar + status.
- Synthetic-fixture smoke test (`tests/test_smoke.py`) that exercises all
  three exporters end-to-end and verifies ZIP layout.

[Unreleased]: https://github.com/djtru/Claude-Chat-Exporter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/djtru/Claude-Chat-Exporter/releases/tag/v1.0.0
