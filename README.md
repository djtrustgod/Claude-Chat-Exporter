# Claude Chat Exporter

<p align="center">
  <img src="assets/logo.png" alt="Claude Chat Exporter logo" width="128" />
</p>

A small Windows-friendly desktop app (CustomTkinter) that turns your
[Claude.ai data export](https://claude.ai/settings/data-privacy-controls)
into shareable, archivable per-chat bundles.

For each conversation you select, the exporter produces a single **ZIP** containing:

```
<chat-name>-<YYYY-MM-DD>.zip
├── <chat-name>.md   (or .docx / .pdf)
└── attachments/
    ├── screenshot-001.png      # inline images are ALSO embedded in the doc
    ├── design-spec.pdf         # non-embeddable files live here, linked from the doc
    ├── notes.txt
    └── MISSING.txt             # listed only when a referenced asset wasn't in the export
```

Images that can be embedded show up inline in the document **and** as files in
`attachments/`. Anything else (PDFs, code files, binaries) lives only in
`attachments/` and is referenced from the document via a relative link.

## Features

- 📂 Load a `conversations.json` from a Claude.ai data export
- 🔎 Search + multi-select your conversations
- 📤 Export each selected chat to **Markdown**, **DOCX**, or **PDF**
- 🖼️ Inline-embeds images AND keeps copies in `attachments/`
- 📎 Preserves non-image attachments as relative-linked files in `attachments/`
- 📝 Renders rich Markdown (headings, lists, tables, code fences, blockquotes, links)
- 🧰 Renders tool-use / tool-result blocks for agentic chats
- 🧵 Background export worker — UI stays responsive
- 🪟 Light/dark/system theme

## Requirements

- Python **3.10+** (tested on 3.12)
- Windows, macOS, or Linux
- Dependencies (auto-installed):
  - `customtkinter`, `python-docx`, `reportlab`, `Pillow`, `markdown-it-py`

No external runtimes needed — no pandoc, no LaTeX, no GTK.

## Install

```powershell
git clone https://github.com/<you>/Claude-Chat-Exporter.git
cd Claude-Chat-Exporter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

## Usage

1. In Claude.ai, go to **Settings → Privacy → Export data** and download your data.
   You'll receive a ZIP. Unzip it — inside you should see `conversations.json`
   and typically a sibling folder containing your attachments and image binaries.
2. In the app, click **Load export…** and pick that `conversations.json`.
3. Use the search box to filter; tick the chats you want to export
   (or use **Select all (visible)**).
4. Pick a format (Markdown / DOCX / PDF) and an output folder.
5. Click **Export N chats**. One ZIP file is written per selected chat.

> [!TIP]
> Keep `conversations.json` next to the original `attachments/` (or
> `files/`) folder from your data export. The app searches sibling folders
> for attachment binaries by filename / file UUID.

## What lives where

```
app.py                          # entry point
src/
├── core/
│   ├── models.py               # Chat / Message / ContentPart / Attachment dataclasses
│   ├── loader.py               # parses conversations.json
│   ├── assets.py               # locates attachment binaries on disk
│   ├── markdown_walker.py      # markdown-it-py → format-agnostic events
│   └── export_service.py       # high-level "export one chat" orchestrator
├── exporters/
│   ├── base.py                 # shared asset-staging logic + Exporter ABC
│   ├── markdown_exporter.py
│   ├── docx_exporter.py        # python-docx
│   └── pdf_exporter.py         # ReportLab
├── packaging/
│   └── zipper.py               # bundles doc + attachments/ into a ZIP
└── gui/
    ├── main_window.py
    └── chat_list_view.py
tests/
└── test_smoke.py               # generates a synthetic export and exports it 3 ways
assets/
├── generate_logo.py            # Pillow script that draws every variant below
├── logo_light.png              # 512×512 — used by the GUI in light mode
├── logo_dark.png               # 512×512 — used by the GUI in dark mode
├── logo.png                    # alias of logo_light.png (README + fallback)
├── logo_64.png                 # 64×64 thumbnail (light variant)
└── logo.ico                    # Multi-resolution Windows taskbar / title-bar icon
```

To tweak the logo (colors, shape), edit [assets/generate_logo.py](assets/generate_logo.py)
and re-run:

```powershell
python assets/generate_logo.py
```

## Run the smoke test

```powershell
python -m unittest tests.test_smoke -v
```

The smoke test generates a fake conversation with text + a PNG + a text
attachment, then runs all three exporters end-to-end and verifies the
produced ZIPs contain the expected files.

## Known limitations

- Live fetching from claude.ai is not supported — only data-export JSON files.
- Multiple chats produce multiple ZIPs (one per chat).
- Image binaries that Claude.ai didn't include in the data export will
  appear as `[Missing image: ...]` placeholders and be listed in
  `attachments/MISSING.txt`.

## License

MIT — see `LICENSE`.
