"""Private Linux parser subprocess; limits are installed before parser imports."""
import json
from pathlib import Path
import resource
import sys


def main():
    # Independent constants keep heavy parser imports behind the hard limits.
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (110, 115))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16_000_000, 16_000_000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from dataclasses import asdict
    from app.services.pdf_extraction import extract_pdf_pages_mupdf, MAX_PAGE_CHARS, MAX_TOTAL_CHARS

    output = Path(sys.argv[2])
    try:
        # OCR child processes are deliberately excluded from this text fallback.
        if sys.argv[3] == "1":
            raise ValueError("Bounded text ingestion does not support OCR subprocesses; use a separately constrained OCR worker.")
        # Start MuPDF with a fresh memory budget rather than importing it only
        # after pypdf has exhausted time/space processing a compressed page.
        pages = extract_pdf_pages_mupdf(Path(sys.argv[1]).read_bytes())
        if any(len(p.text) > MAX_PAGE_CHARS for p in pages) or sum(len(p.text) for p in pages) > MAX_TOTAL_CHARS:
            raise ValueError("PDF output text limit exceeded.")
        payload = {"pages": [asdict(page) for page in pages]}
    except Exception as exc:
        # Only controlled type/message; never emit document text or tracebacks.
        causes = []
        cause = exc
        while cause is not None and len(causes) < 4:
            causes.append(type(cause).__name__)
            cause = cause.__cause__
        payload = {"error": f"{type(exc).__name__}: {str(exc)[:300]}; causes={' -> '.join(causes)}"}
        output.write_text(json.dumps(payload), encoding="utf-8")
        return 1
    output.write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
