"""End-to-end smoke test for the export pipeline.

Generates a tiny synthetic Claude.ai data export (conversations.json + an
attachments folder with a PNG and a text file) and exercises all three
exporters. Verifies that each produces a ZIP with the expected layout.

Run with:
    python -m unittest tests.test_smoke
"""

from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from src.core.export_service import OutputFormat, export_chat
from src.core.loader import load_export


_SAMPLE_CONVERSATIONS = [
    {
        "uuid": "conv-001",
        "name": "Smoke test: rendering features",
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:30:00Z",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "created_at": "2026-05-20T10:00:00Z",
                "text": "Hello! Here's a screenshot and a file.",
                "attachments": [
                    {
                        "file_name": "notes.txt",
                        "file_type": "text/plain",
                        "extracted_content": "These are some notes\nthat Claude extracted.",
                    }
                ],
                "files": [
                    {
                        "file_name": "screenshot.png",
                        "file_uuid": "img-uuid-1",
                        "media_type": "image/png",
                    }
                ],
            },
            {
                "uuid": "msg-2",
                "sender": "assistant",
                "created_at": "2026-05-20T10:01:00Z",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "# A heading\n"
                            "\n"
                            "Here is **bold** and *italic* and `inline code` and a "
                            "[link](https://example.com).\n"
                            "\n"
                            "- list item one\n"
                            "- list item two with `code`\n"
                            "\n"
                            "```python\n"
                            "def hello():\n"
                            "    print('hi')\n"
                            "```\n"
                            "\n"
                            "| Col A | Col B |\n"
                            "| --- | --- |\n"
                            "| 1 | 2 |\n"
                            "| 3 | 4 |\n"
                            "\n"
                            "> A blockquote with **emphasis**.\n"
                        ),
                    }
                ],
            },
            {
                "uuid": "msg-3",
                "sender": "assistant",
                "created_at": "2026-05-20T10:02:00Z",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "file_uuid": "img-uuid-1",
                            "file_name": "screenshot.png",
                            "media_type": "image/png",
                        },
                        "alt": "Sample screenshot",
                    }
                ],
            },
        ],
    }
]


def _write_fixture(export_root: Path) -> Path:
    """Write conversations.json + an attachments/ folder. Returns the JSON path."""
    json_path = export_root / "conversations.json"
    json_path.write_text(json.dumps(_SAMPLE_CONVERSATIONS), encoding="utf-8")

    attachments = export_root / "attachments"
    attachments.mkdir(parents=True, exist_ok=True)

    # Sample PNG (a tiny solid-colour rectangle)
    img = Image.new("RGB", (160, 90), color=(70, 130, 180))
    img.save(attachments / "screenshot.png", format="PNG")

    # Sample text attachment binary
    (attachments / "notes.txt").write_text(
        "These are some real notes on disk\n", encoding="utf-8"
    )
    return json_path


class SmokeTest(unittest.TestCase):
    def test_all_three_formats_produce_valid_zips(self) -> None:
        with TemporaryDirectory(prefix="cce-test-") as tmp:
            tmp_root = Path(tmp)
            export_root = tmp_root / "export"
            export_root.mkdir()
            output_dir = tmp_root / "out"
            output_dir.mkdir()

            json_path = _write_fixture(export_root)
            chats = load_export(json_path)
            self.assertEqual(len(chats), 1, "loader should parse exactly one chat")

            for fmt in (OutputFormat.MARKDOWN, OutputFormat.DOCX, OutputFormat.PDF):
                with self.subTest(fmt=fmt):
                    outcome = export_chat(
                        chat=chats[0],
                        fmt=fmt,
                        output_dir=output_dir,
                        export_root=export_root,
                    )
                    self.assertTrue(outcome.zip_path.exists(), "ZIP must exist")
                    self.assertGreater(outcome.zip_path.stat().st_size, 0)

                    with zipfile.ZipFile(outcome.zip_path) as zf:
                        names = zf.namelist()
                        doc_ext = {
                            OutputFormat.MARKDOWN: ".md",
                            OutputFormat.DOCX: ".docx",
                            OutputFormat.PDF: ".pdf",
                        }[fmt]
                        self.assertTrue(
                            any(n.endswith(doc_ext) for n in names),
                            f"missing {doc_ext} doc in {names}",
                        )
                        self.assertTrue(
                            any(n.startswith("attachments/screenshot") for n in names),
                            f"missing staged screenshot in {names}",
                        )
                        self.assertTrue(
                            any("notes" in n.lower() for n in names),
                            f"missing notes attachment in {names}",
                        )
                        self.assertFalse(
                            any(n.endswith("MISSING.txt") for n in names),
                            f"unexpected MISSING.txt in {names}",
                        )


if __name__ == "__main__":
    unittest.main()
