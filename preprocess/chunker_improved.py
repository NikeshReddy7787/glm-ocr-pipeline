"""
preprocess/chunker.py (Improved)

1. Recursively find all PDFs in a directory
2. Validate PDF file size (skip if > 50 MB)
3. If a PDF has > CHUNK_SIZE pages, split it into chunks
4. Return a flat list of (file_to_process, source_pdf_stem)
   so the runner knows which source PDF each item belongs to
"""

import logging
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

CHUNK_SIZE      = 90    # stay under GLM-OCR's 100-page hard limit
MAX_PDF_SIZE_MB = 50    # 50 MB limit for GLM-OCR processing
CHUNKS_TMP_DIR  = "./pdf_chunks"

logger = logging.getLogger("glm_ocr_pipeline")


def discover_pdfs(root: str) -> list[Path]:
    """Recursively find all PDF files in root directory."""
    root_path = Path(root)
    
    try:
        pdfs = sorted(root_path.rglob("*.pdf"))
    except PermissionError as e:
        logger.error(f"Permission denied accessing {root}: {e}")
        return []
    except OSError as e:
        logger.error(f"Error scanning directory {root}: {e}")
        return []

    logger.info(f"Scanning: {root_path}")
    logger.info(f"PDFs found: {len(pdfs)}")
    
    for p in pdfs:
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
            logger.debug(f"  · {p.relative_to(root_path)}  ({size_mb:.1f}MB)")
        except OSError:
            logger.debug(f"  · {p.relative_to(root_path)}  (size unknown)")

    return pdfs


def _validate_pdf_size(pdf: Path) -> bool:
    """Check if PDF file size is within limits."""
    try:
        size_mb = pdf.stat().st_size / (1024 * 1024)
    except OSError as e:
        logger.warning(f"  ⚠  Cannot check size of {pdf.name}: {e}")
        return True  # Allow to attempt processing
    
    if size_mb > MAX_PDF_SIZE_MB:
        logger.warning(
            f"  ⚠  SKIP {pdf.name} — {size_mb:.1f}MB exceeds {MAX_PDF_SIZE_MB}MB limit"
        )
        return False
    
    return True


def _split(pdf: Path, chunk_size: int, tmp_dir: str) -> list[Path]:
    """
    Split one large PDF into chunk_size-page pieces.
    Returns list of chunk file paths (may be empty if read fails).
    """
    out = Path(tmp_dir) / pdf.stem
    
    try:
        out.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.error(f"  ✗ Cannot create chunk directory {out}: {e}")
        return []

    try:
        reader = PdfReader(str(pdf))
    except Exception as e:
        logger.error(f"  ✗ Cannot read PDF {pdf.name}: {e}")
        return []
    
    total = len(reader.pages)
    chunks = []

    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        n = (start // chunk_size) + 1
        name = f"{pdf.stem}__chunk{n:03d}_p{start+1:04d}-p{end:04d}.pdf"
        path = out / name

        try:
            writer = PdfWriter()
            for page in reader.pages[start:end]:
                writer.add_page(page)
            
            with open(path, "wb") as f:
                writer.write(f)
            
            chunks.append(path)
            logger.debug(
                f"    ✂  chunk {n}: pages {start+1}–{end}  →  {name}"
            )
        except (OSError, PermissionError, Exception) as e:
            logger.error(f"    ✗ Failed to write chunk {n}: {e}")
            continue

    if not chunks:
        logger.error(f"  ✗ No chunks were successfully created for {pdf.name}")
        return []
    
    logger.info(f"    ✓ Created {len(chunks)} chunk(s)")
    return chunks


def build_queue(
    pdfs: list[Path],
    chunk_size: int = CHUNK_SIZE,
    tmp_dir: str = CHUNKS_TMP_DIR,
) -> list[tuple[Path, str]]:
    """
    Returns list of (pdf_to_process, source_stem).
    source_stem is the original PDF name — used to group outputs later.
    
    Validates file size and attempts to read page count.
    Splits large PDFs into chunks.
    Skips invalid PDFs with detailed warnings.
    """
    queue = []
    skipped = []

    logger.info(f"\n{'─'*60}")
    logger.info(f"Checking page counts (limit: {chunk_size} pages/chunk, size: {MAX_PDF_SIZE_MB}MB max)")
    logger.info(f"{'─'*60}")

    for pdf in pdfs:
        # Step 1: Validate file size
        if not _validate_pdf_size(pdf):
            skipped.append((pdf.name, f"exceeds {MAX_PDF_SIZE_MB}MB"))
            continue
        
        # Step 2: Try to read page count
        try:
            reader = PdfReader(str(pdf))
            pages = len(reader.pages)
        except Exception as e:
            logger.warning(f"  ⚠  SKIP {pdf.name} — cannot read: {e}")
            skipped.append((pdf.name, f"read error: {e}"))
            continue

        # Step 3: Decide: process as-is or chunk
        if pages <= chunk_size:
            logger.info(f"  ✓ {pdf.name}  ({pages} pages) — will process as-is")
            queue.append((pdf, pdf.stem))
        else:
            n_chunks = -(-pages // chunk_size)
            logger.info(
                f"  ✂  {pdf.name}  ({pages} pages → {n_chunks} chunk(s))"
            )
            chunks = _split(pdf, chunk_size, tmp_dir)
            if chunks:
                for chunk in chunks:
                    queue.append((chunk, pdf.stem))
            else:
                logger.error(f"    ✗ Failed to chunk {pdf.name}")
                skipped.append((pdf.name, "chunking failed"))

    logger.info(f"\n{'─'*60}")
    logger.info(f"Queue: {len(queue)} item(s) ready")
    if skipped:
        logger.warning(f"Skipped: {len(skipped)} file(s)")
        for name, reason in skipped:
            logger.debug(f"  - {name}: {reason}")
    logger.info(f"{'─'*60}\n")
    
    return queue


def cleanup(tmp_dir: str = CHUNKS_TMP_DIR) -> None:
    """Remove temporary chunk directory."""
    p = Path(tmp_dir)
    if p.exists():
        try:
            shutil.rmtree(p)
            logger.info(f"Cleaned up temp chunks: {tmp_dir}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not remove temp directory {tmp_dir}: {e}")
    else:
        logger.debug(f"Temp directory does not exist (nothing to clean): {tmp_dir}")
