"""
Document conversion helpers for the ingestion pipeline.

Functions:
- convert_pptx_to_pdf: uses LibreOffice headless to convert PPTX to PDF.
- convert_epub_to_text: extracts readable text from an EPUB via ebooklib.
- extract_images_from_pdf: saves large images from a PDF using PyMuPDF.
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # type: ignore[import-untyped]  # PyMuPDF

logger = logging.getLogger(__name__)


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        return "\n".join(self._chunks)


def convert_pptx_to_pdf(path: str | Path, output_dir: Optional[Path] = None) -> Path:
    """
    Convert a PPTX file to PDF using LibreOffice (headless).

    Args:
        path: input PPTX path.
        output_dir: optional directory for the PDF (defaults to same folder).

    Returns:
        Path to the generated PDF.

    Raises:
        FileNotFoundError: if the PPTX does not exist.
        RuntimeError: if LibreOffice conversion fails or is missing.
    """
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"File PPTX non trovato: {input_path}")

    out_dir = output_dir or input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(input_path),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,  # explicit for clarity/safety
        )  # nosec B603
    except FileNotFoundError as exc:
        raise RuntimeError("LibreOffice (soffice) non trovato nel PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Conversione PPTX->PDF fallita: {exc.stderr.decode(errors='ignore')}"
        ) from exc

    pdf_path = out_dir / f"{input_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError("Conversione PPTX->PDF non ha prodotto il file atteso")
    return pdf_path


def pptx_to_pdf_with_powerpoint(
    path: str | Path, output_dir: Optional[Path] = None
) -> Path:
    """
    Convert a PPTX to PDF using Microsoft PowerPoint via COM automation (Windows only).

    Requires:
      - PowerPoint installed
      - pywin32 (pip install pywin32)
    """
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pywin32 non installato: pip install pywin32") from exc

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"File PPTX non trovato: {input_path}")

    out_dir = output_dir or input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{input_path.stem}.pdf"

    ppt = win32com.client.Dispatch("PowerPoint.Application")
    ppt.Visible = 1
    presentation = ppt.Presentations.Open(str(input_path), WithWindow=False)
    try:
        presentation.SaveAs(str(out_path), 32)  # 32 = PDF format
    finally:
        presentation.Close()
        ppt.Quit()

    if not out_path.exists():
        raise RuntimeError("PowerPoint non ha generato il PDF atteso")
    return out_path


def convert_epub_to_text(path: str | Path) -> str:
    """
    Extract plain text from an EPUB using ebooklib.

    Args:
        path: input EPUB path.

    Returns:
        Extracted text (one block per HTML segment separated by newlines).
    """
    try:
        from ebooklib import epub  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("ebooklib non installato: pip install ebooklib") from exc

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"File EPUB non trovato: {input_path}")

    book = epub.read_epub(str(input_path))
    segments: List[str] = []

    for item in book.get_items():
        if item.get_type() == getattr(
            epub, "ITEM_DOCUMENT", 9
        ):  # 9 is ITEM_DOCUMENT in ebooklib
            stripper = _HTMLStripper()
            content_bytes: bytes = item.get_content()
            try:
                content_str = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                content_str = str(content_bytes)
            stripper.feed(content_str)
            text = stripper.get_text()
            if text:
                segments.append(text)

    return "\n\n".join(segments)


def extract_images_from_pdf(
    path: str | Path,
    output_dir: Optional[Path] = None,
    min_size: Tuple[int, int] = (500, 500),
) -> List[Path]:
    """
    Extract and save images from a PDF that exceed a minimum size.

    Args:
        path: input PDF path.
        output_dir: folder where images will be saved (defaults to `<stem>_images`).
        min_size: (width, height) threshold; images smaller than this are skipped.

    Returns:
        List of saved image paths.
    """
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"File PDF non trovato: {input_path}")

    out_dir = output_dir or input_path.parent / f"{input_path.stem}_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(input_path))  # type: ignore[attr-defined]
    saved: List[Path] = []
    min_w, min_h = min_size

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            img_dict = doc.extract_image(xref)
            width = img_dict.get("width", 0)
            height = img_dict.get("height", 0)
            if width < min_w or height < min_h:
                continue

            image_bytes: bytes = img_dict["image"]
            ext = img_dict.get("ext", "png")
            filename = f"{input_path.stem}_p{page_index+1}_i{img_index+1}.{ext}"
            out_path = out_dir / filename
            out_path.write_bytes(image_bytes)
            saved.append(out_path)

    return saved


__all__ = [
    "convert_pptx_to_pdf",
    "pptx_to_pdf_with_powerpoint",
    "convert_epub_to_text",
    "extract_images_from_pdf",
]
