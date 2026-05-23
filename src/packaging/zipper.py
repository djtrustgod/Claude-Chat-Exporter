"""Bundle a rendered chat (doc + attachments/) into a ZIP archive."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


def build_zip(
    output_dir: Path,
    slug: str,
    doc_path: Path,
    attachments_dir: Path | None,
    archive_date: datetime | None = None,
) -> Path:
    """Create ``<output_dir>/<slug>-<YYYY-MM-DD>.zip``.

    The ZIP contains:
        <slug>.<ext>
        attachments/...   (only if ``attachments_dir`` exists and is non-empty)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_part = (archive_date or datetime.now()).strftime("%Y-%m-%d")
    zip_path = _unique_path(output_dir / f"{slug}-{date_part}.zip")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(doc_path, arcname=doc_path.name)
        if attachments_dir is not None and attachments_dir.is_dir():
            for path in sorted(attachments_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(attachments_dir.parent)
                zf.write(path, arcname=str(rel).replace("\\", "/"))
    return zip_path


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1
