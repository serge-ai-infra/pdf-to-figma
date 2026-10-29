"""The one place this project calls poppler from Python rather than a shell
script (`scripts/probe-pdf.sh` already called it from bash). Bytes in,
string out, over stdin/stdout pipes — no temp file, no path ever touches
disk, so this stays as filesystem-free as `extract/pdf.py` despite spawning
a process. See `docs/architecture.md`'s stack section for the license
reasoning (execution, not linking) this relies on.
"""

from __future__ import annotations

import shutil
import subprocess

_TIMEOUT_SECONDS = 60


class ConvertError(Exception):
    """Raised when poppler is missing, hangs, or a page can't be converted."""


def page_to_svg(pdf_bytes: bytes, page: int) -> str:
    """Convert one page of a PDF to SVG. Vector, full page — cropping is
    `donor.py`'s job, not poppler's: `-x/-y/-W/-H` only affect raster output,
    confirmed by direct testing (see spec's Risks)."""
    if shutil.which("pdftocairo") is None:
        raise ConvertError("pdftocairo not found — install poppler (brew install poppler)")

    try:
        result = subprocess.run(
            ["pdftocairo", "-svg", "-f", str(page), "-l", str(page), "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConvertError(
            f"pdftocairo did not finish page {page} within {_TIMEOUT_SECONDS}s"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ConvertError(f"pdftocairo failed on page {page}: {stderr}") from exc

    return result.stdout.decode("utf-8")
