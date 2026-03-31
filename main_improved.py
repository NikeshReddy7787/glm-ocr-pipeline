"""
GLM-OCR Pipeline (Improved)
Usage:
    python main.py /kaggle/input/10K10Q
    python main.py /kaggle/input/10K10Q --output /kaggle/working/ocr_results
    python main.py /kaggle/input/10K10Q --no-save --verbose
    python main.py /kaggle/input/10K10Q --tmp-dir /tmp/my_chunks
"""

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from glmocr import GlmOcr

from preprocess import discover_pdfs, build_queue, cleanup
from postprocess import merge


# ─── LOGGING SETUP ─────────────────────────────────────────────────────────
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging with console output."""
    logger = logging.getLogger("glm_ocr_pipeline")
    logger.handlers.clear()  # Remove any existing handlers
    
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


logger = logging.getLogger("glm_ocr_pipeline")


# ─── VALIDATION FUNCTIONS ─────────────────────────────────────────────────
def validate_dataset_path(path_str: str) -> Path:
    """Validate that dataset path exists and is readable."""
    try:
        path = Path(path_str).resolve()
    except (OSError, ValueError) as e:
        logger.error(f"Invalid path format: {path_str} — {e}")
        sys.exit(1)
    
    if not path.exists():
        logger.error(f"Dataset path does not exist: {path}")
        sys.exit(1)
    
    if not path.is_dir():
        logger.error(f"Dataset path is not a directory: {path}")
        sys.exit(1)
    
    # Check read permissions
    try:
        _ = list(path.iterdir())
    except PermissionError:
        logger.error(f"Permission denied reading: {path}")
        sys.exit(1)
    
    logger.info(f"Dataset path validated: {path}")
    return path


def validate_output_path(path_str: str) -> Path:
    """Prepare output directory."""
    try:
        path = Path(path_str).resolve()
    except (OSError, ValueError) as e:
        logger.error(f"Invalid output path format: {path_str} — {e}")
        sys.exit(1)
    
    try:
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.error(f"Cannot create output directory: {path} — {e}")
        sys.exit(1)
    
    logger.info(f"Output directory: {path}")
    return path


def validate_tmp_dir(path_str: str) -> Path:
    """Prepare temp directory for chunks."""
    try:
        path = Path(path_str).resolve()
    except (OSError, ValueError) as e:
        logger.error(f"Invalid temp dir path: {path_str} — {e}")
        sys.exit(1)
    
    try:
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        logger.error(f"Cannot create temp directory: {path} — {e}")
        sys.exit(1)
    
    logger.debug(f"Temp directory: {path}")
    return path


def check_disk_space(path: Path, required_mb: int = 100) -> bool:
    """Check if sufficient free disk space available."""
    try:
        stat = shutil.disk_usage(path)
        free_mb = stat.free / (1024 * 1024)
        if free_mb < required_mb:
            logger.warning(f"Low disk space: {free_mb:.0f}MB free (need ~{required_mb}MB)")
            return False
        logger.debug(f"Disk space OK: {free_mb:.0f}MB available")
        return True
    except OSError as e:
        logger.warning(f"Could not check disk space: {e}")
        return True


def test_api_connection(config_path: str) -> bool:
    """Test if GLM-OCR API is reachable."""
    try:
        logger.info("Testing API connection...")
        with GlmOcr(config_path=config_path, log_level="WARNING") as ocr:
            # A quick no-op to test connection
            logger.info("✓ API connection successful")
            return True
    except Exception as e:
        logger.error(f"API connection failed: {e}")
        logger.error("Ensure the OCR server is running and accessible")
        return False


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="GLM-OCR — Reliable PDF Dataset Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py /path/to/pdfs
  python main.py /path/to/pdfs --output ./results --tmp-dir /tmp/chunks
  python main.py /path/to/pdfs --no-save --verbose
  python main.py /path/to/pdfs --keep-chunks
        """
    )
    parser.add_argument(
        "dataset",
        help="Root directory containing PDFs (recurses all subdirs)"
    )
    parser.add_argument(
        "--output", "-o",
        default="./ocr_results",
        help="Output directory (default: ./ocr_results)"
    )
    parser.add_argument(
        "--tmp-dir",
        default="./pdf_chunks",
        help="Temp directory for chunk PDFs (default: ./pdf_chunks)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print OCR output only, don't write files"
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Keep temp chunk PDFs after processing"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--config",
        default="conf.yaml",
        help="Path to GLM-OCR config (default: conf.yaml)"
    )
    parser.add_argument(
        "--skip-api-check",
        action="store_true",
        help="Skip API connectivity test (faster startup)"
    )
    
    args = parser.parse_args()
    
    # ── Setup ──────────────────────────────────────────────────────────────
    setup_logging(verbose=args.verbose)
    logger.info("=" * 70)
    logger.info("GLM-OCR Pipeline (Improved)")
    logger.info("=" * 70)
    
    # Validate paths
    dataset_path = validate_dataset_path(args.dataset)
    output_path  = validate_output_path(args.output)
    tmp_path     = validate_tmp_dir(args.tmp_dir)
    
    check_disk_space(dataset_path, required_mb=100)
    
    # ── Preprocess ─────────────────────────────────────────────────────────
    logger.info("\n[1/4] 🔍 Discovering PDFs...")
    pdfs = discover_pdfs(str(dataset_path))
    
    if not pdfs:
        logger.error("No PDF files found in dataset directory")
        sys.exit(1)
    
    logger.info(f"\nFound {len(pdfs)} PDF(s)")
    
    logger.info("\n[2/4] 📋 Building processing queue...")
    queue = build_queue(pdfs, tmp_dir=str(tmp_path))
    
    if not queue:
        logger.error("Processing queue is empty — nothing to process")
        sys.exit(1)
    
    logger.info(f"Queue ready: {len(queue)} item(s) to process")
    
    # ── API Check ──────────────────────────────────────────────────────────
    if not args.skip_api_check:
        logger.info("\n[3/4a] 🔌 Testing API connectivity...")
        if not test_api_connection(args.config):
            sys.exit(1)
    
    # ── OCR Processing ────────────────────────────────────────────────────
    logger.info("\n[3/4] ⚙️  Processing with GLM-OCR...")
    logger.info("-" * 70)
    
    all_times    = []
    source_stems = set()
    failed_pdfs  = []
    
    try:
        with GlmOcr(config_path=args.config, log_level="ERROR") as ocr:
            for i, (pdf_path, source_stem) in enumerate(queue, 1):
                logger.info(f"[{i}/{len(queue)}] Processing: {pdf_path.name}")
                
                try:
                    t0      = time.time()
                    result  = ocr.parse(str(pdf_path))
                    elapsed = round(time.time() - t0, 2)
                    all_times.append(elapsed)
                    
                    if not args.no_save:
                        save_dir = output_path / pdf_path.stem
                        try:
                            save_dir.mkdir(parents=True, exist_ok=True)
                            result.save(output_dir=str(save_dir))
                        except (OSError, PermissionError) as e:
                            logger.error(f"  Failed to save results: {e}")
                            failed_pdfs.append((pdf_path.name, f"Save error: {e}"))
                            continue
                        
                        # Track stems for merge
                        if "__chunk" in pdf_path.stem:
                            source_stems.add(source_stem)
                    
                    logger.info(f"  ✓ Completed in {elapsed}s")
                    logger.debug(f"Output:\n{result}")
                
                except Exception as e:
                    logger.error(f"  ✗ Processing failed: {e}")
                    failed_pdfs.append((pdf_path.name, str(e)))
    
    except Exception as e:
        logger.critical(f"Unexpected error during OCR processing: {e}")
        sys.exit(1)
    
    # ── Postprocess — Merge Chunks ────────────────────────────────────────
    if source_stems and not args.no_save:
        logger.info("\n[4/4] 🔗 Merging chunk outputs...")
        try:
            merge(output_dir=str(output_path), source_stems=source_stems)
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            failed_pdfs.append(("MERGE", str(e)))
    
    # ── Cleanup ─────────────────────────────────────────────────────────────
    if not args.keep_chunks:
        logger.info("\n🧹 Cleaning up temporary chunks...")
        cleanup(tmp_dir=str(tmp_path))
    
    # ── Summary Report ──────────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    
    successful = len(all_times)
    total_files = len(queue)
    
    if all_times:
        total_time = sum(all_times)
        avg_time   = total_time / len(all_times)
        logger.info(f"✓ Completed: {successful}/{total_files} files")
        logger.info(f"  Total time  : {total_time:.1f}s")
        logger.info(f"  Avg / file  : {avg_time:.1f}s")
        if not args.no_save:
            logger.info(f"  Output      : {output_path}/")
    
    if failed_pdfs:
        logger.warning(f"\n✗ {len(failed_pdfs)} file(s) failed:")
        for name, error in failed_pdfs:
            logger.warning(f"  - {name}: {error}")
    
    # Save processing report
    if not args.no_save:
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_processed": successful,
            "total_files": total_files,
            "total_time_s": round(sum(all_times), 2) if all_times else 0,
            "failed": [{"file": name, "error": err} for name, err in failed_pdfs],
            "output_dir": str(output_path),
        }
        report_path = output_path / "processing_report.json"
        try:
            report_path.write_text(json.dumps(report, indent=2))
            logger.info(f"\nReport saved: {report_path}")
        except Exception as e:
            logger.error(f"Could not save report: {e}")
    
    logger.info("=" * 70)
    
    # Exit code
    if failed_pdfs:
        sys.exit(1)


if __name__ == "__main__":
    main()
