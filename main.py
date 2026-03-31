"""
GLM-OCR Pipeline
Usage:
    python main.py /kaggle/input/10K10Q
    python main.py /kaggle/input/10K10Q --output /kaggle/working/ocr_results
    python main.py /kaggle/input/10K10Q --no-save
    python main.py /kaggle/input/10K10Q --keep-chunks
"""

import argparse
import sys
import time
from pathlib import Path

from glmocr import GlmOcr

from preprocess  import discover_pdfs, build_queue, cleanup
from postprocess import merge


def main():
    parser = argparse.ArgumentParser(description="GLM-OCR — PDF Dataset Processor")
    parser.add_argument("dataset",      help="Root directory containing PDFs (recurses all subdirs)")
    parser.add_argument("--output","-o",default="./ocr_results",
                        help="Output directory (default: ./ocr_results)")
    parser.add_argument("--no-save",    action="store_true",
                        help="Print OCR output only, don't write files")
    parser.add_argument("--keep-chunks",action="store_true",
                        help="Keep temp chunk PDFs after processing")
    args = parser.parse_args()

    # ── Preprocess ─────────────────────────────────────────────────────────────
    pdfs  = discover_pdfs(args.dataset)
    queue = build_queue(pdfs)   # [(pdf_path, source_stem), ...]

    if not queue:
        print("Nothing to process.")
        sys.exit(1)

    print(f"\n🔍 GLM-OCR Pipeline")
    print(f"   Files  : {len(queue)}")
    print(f"   Output : {args.output}\n")
    print("─" * 60)

    # ── OCR ────────────────────────────────────────────────────────────────────
    all_times    = []
    source_stems = set()   # track which stems had chunks → for merge step

    with GlmOcr(config_path="conf.yaml", log_level="DEBUG") as ocr:
        for i, (pdf_path, source_stem) in enumerate(queue, 1):
            print(f"[{i}/{len(queue)}] {pdf_path.name}  (source: {source_stem})")
            try:
                t0      = time.time()
                result  = ocr.parse(str(pdf_path))
                elapsed = round(time.time() - t0, 2)
                all_times.append(elapsed)

                if not args.no_save:
                    # Save into a subfolder named after the chunk file
                    save_dir = Path(args.output) / pdf_path.stem
                    save_dir.mkdir(parents=True, exist_ok=True)
                    result.save(output_dir=str(save_dir))

                    # Track stems that were chunked so we merge them later
                    if "__chunk" in pdf_path.stem:
                        source_stems.add(source_stem)

                print(f"  ✅ Done in {elapsed}s")
                print(f"\n{'─'*40} OCR OUTPUT {'─'*40}")
                print(result)
                print("─" * 91)

            except Exception as e:
                print(f"  ❌ Error: {e}")

            print()

    # ── Postprocess — merge chunks back per source PDF ─────────────────────────
    if source_stems and not args.no_save:
        merge(output_dir=args.output, source_stems=source_stems)

    # ── Cleanup temp split PDFs ────────────────────────────────────────────────
    if not args.keep_chunks:
        cleanup()

    # ── Summary ────────────────────────────────────────────────────────────────
    if all_times:
        total = sum(all_times)
        print("─" * 60)
        print(f"✅ Completed {len(all_times)}/{len(queue)}")
        print(f"   Total time : {round(total, 2)}s")
        print(f"   Avg / file : {round(total / len(all_times), 2)}s")
        if not args.no_save:
            print(f"   Results in : {args.output}/")


if __name__ == "__main__":
    main()
