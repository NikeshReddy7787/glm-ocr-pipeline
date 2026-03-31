"""
preprocess/chunker.py

1. Recursively find all PDFs in a directory
2. If a PDF has > CHUNK_SIZE pages, split it into chunks
3. Return a flat list of (file_to_process, source_pdf_stem)
   so the runner knows which source PDF each item belongs to
"""

import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

CHUNK_SIZE     = 90    # stay under GLM-OCR's 100-page hard limit
CHUNKS_TMP_DIR = "./pdf_chunks"


def discover_pdfs(root: str) -> list[Path]:
    root_path = Path(root)
    pdfs = sorted(root_path.rglob("*.pdf"))

    print(f"\n📂 Scanning : {root}")
    print(f"   PDFs found: {len(pdfs)}")
    for p in pdfs:
        print(f"   · {p.relative_to(root_path)}")

    return pdfs


def _split(pdf: Path, chunk_size: int, tmp_dir: str) -> list[Path]:
    """Split one large PDF into chunk_size-page pieces."""
    out = Path(tmp_dir) / pdf.stem
    out.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf))
    total  = len(reader.pages)
    chunks = []

    for start in range(0, total, chunk_size):
        end     = min(start + chunk_size, total)
        n       = (start // chunk_size) + 1
        name    = f"{pdf.stem}__chunk{n:03d}_p{start+1:04d}-p{end:04d}.pdf"
        path    = out / name

        writer = PdfWriter()
        for page in reader.pages[start:end]:
            writer.add_page(page)
        with open(path, "wb") as f:
            writer.write(f)

        chunks.append(path)
        print(f"    ✂  chunk {n}: pages {start+1}–{end}  →  {name}")

    return chunks


def build_queue(
    pdfs: list[Path],
    chunk_size: int = CHUNK_SIZE,
    tmp_dir: str    = CHUNKS_TMP_DIR,
) -> list[tuple[Path, str]]:
    """
    Returns list of (pdf_to_process, source_stem).
    source_stem is the original PDF name — used to group outputs later.
    """
    queue = []

    print(f"\n{'─'*55}")
    print(f"🔎  Checking page counts  (limit: {chunk_size} pages/chunk)")
    print(f"{'─'*55}")

    for pdf in pdfs:
        try:
            pages = len(PdfReader(str(pdf)).pages)
        except Exception as e:
            print(f"  ⚠  SKIP {pdf.name} — {e}")
            continue

        if pages <= chunk_size:
            print(f"  ✅  {pdf.name}  ({pages} pages) — sending as-is")
            queue.append((pdf, pdf.stem))
        else:
            n_chunks = -(-pages // chunk_size)
            print(f"  ✂   {pdf.name}  ({pages} pages → {n_chunks} chunks)")
            for chunk in _split(pdf, chunk_size, tmp_dir):
                queue.append((chunk, pdf.stem))   # keep parent stem

    print(f"\n   Queue size: {len(queue)} item(s)\n")
    return queue


def cleanup(tmp_dir: str = CHUNKS_TMP_DIR) -> None:
    p = Path(tmp_dir)
    if p.exists():
        shutil.rmtree(p)
        print(f"🧹  Removed tmp chunks: {tmp_dir}")
