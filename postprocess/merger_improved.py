"""
postprocess/merger.py (Improved)

After OCR runs on each chunk, merge all chunk outputs that belong
to the same source PDF into a single file.

Folder layout produced by result.save():
    <output_dir>/
        apple_10K__chunk001_p0001-p0090/   ← one folder per chunk
            *.md
            *.json
        apple_10K__chunk002_p0091-p0180/
            *.md
            *.json

After merge():
    <output_dir>/
        apple_10K_merged.md      ← all pages in order
        apple_10K_merged.json    ← list of per-chunk JSON objects
        apple_10K_merged_info.json  ← metadata (chunk count, etc)
        apple_10K__chunk001_.../   (originals kept for reference)
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("glm_ocr_pipeline")


def merge(output_dir: str, source_stems: set[str]) -> None:
    """
    For every source PDF stem, find all its chunk sub-folders,
    sort them by chunk number, and concatenate their .md / .json outputs.
    """
    out = Path(output_dir)
    
    logger.info(f"\n{'─'*60}")
    logger.info(f"Merging {len(source_stems)} source PDF(s)")
    logger.info(f"{'─'*60}")

    merge_stats = []

    for stem in sorted(source_stems):
        # Find all subdirs that belong to this source PDF
        # They are named <stem>__chunk*
        try:
            chunk_dirs = sorted(out.glob(f"{stem}__chunk*"))
        except OSError as e:
            logger.error(f"  ✗ Cannot access chunks for {stem}: {e}")
            continue

        if not chunk_dirs:
            # PDF wasn't chunked — nothing to merge
            logger.debug(f"  ℹ  No chunks found for {stem}")
            continue

        logger.info(f"\n  📄 {stem}  ({len(chunk_dirs)} chunk(s))")

        md_files, json_files = _merge_markdown(stem, chunk_dirs, out)
        json_count = _merge_json(stem, chunk_dirs, out)
        _save_merge_info(stem, out, len(chunk_dirs), md_files, json_count)
        
        merge_stats.append({
            "stem": stem,
            "chunks": len(chunk_dirs),
            "md_files": md_files,
            "json_files": json_count,
        })

    logger.info(f"\n{'─'*60}")
    logger.info(f"Merge completed: {len(merge_stats)} source(s) processed")
    for stat in merge_stats:
        logger.info(
            f"  · {stat['stem']}: {stat['chunks']} chunks → "
            f"{stat['md_files']} MD, {stat['json_files']} JSON"
        )
    logger.info(f"{'─'*60}")


def _merge_markdown(
    stem: str,
    chunk_dirs: list[Path],
    out: Path,
) -> tuple[int, list[Path]]:
    """
    Merge all .md files from chunks into a single _merged.md file.
    Returns (number of MD files merged, list of merged file paths).
    """
    merged_md = out / f"{stem}_merged.md"
    parts = []
    md_count = 0

    for chunk_dir in chunk_dirs:
        try:
            md_files = sorted(chunk_dir.glob("*.md"))
        except OSError as e:
            logger.warning(f"    ⚠  Cannot read {chunk_dir.name}: {e}")
            continue
        
        for md in md_files:
            try:
                content = md.read_text(encoding="utf-8")
                parts.append(content)
                md_count += 1
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"    ⚠  Cannot read {md.name}: {e}")

    if parts:
        try:
            merged_md.write_text("\n\n".join(parts), encoding="utf-8")
            logger.info(f"    ✓ MD  → {merged_md.name}  ({md_count} files merged)")
            return md_count, [merged_md]
        except (OSError, PermissionError) as e:
            logger.error(f"    ✗ Failed to write {merged_md.name}: {e}")
            return 0, []
    else:
        logger.warning(f"    ⚠  No .md files found for {stem}")
        return 0, []


def _merge_json(
    stem: str,
    chunk_dirs: list[Path],
    out: Path,
) -> int:
    """
    Merge all .json files from chunks into one _merged.json file.
    Each original JSON is preserved with its chunk metadata.
    Returns: count of JSON files merged.
    """
    merged_json = out / f"{stem}_merged.json"
    combined = []
    json_count = 0

    for chunk_dir in chunk_dirs:
        try:
            json_files = sorted(chunk_dir.glob("*.json"))
        except OSError as e:
            logger.warning(f"    ⚠  Cannot read {chunk_dir.name}: {e}")
            continue
        
        for jf in json_files:
            try:
                json_text = jf.read_text(encoding="utf-8")
                data = json.loads(json_text)
                
                # Wrap each JSON with metadata about which chunk it came from
                combined.append({
                    "chunk_dir": chunk_dir.name,
                    "source_file": jf.name,
                    "data": data,
                })
                json_count += 1
            except FileNotFoundError:
                logger.warning(f"    ⚠  File disappeared: {jf.name}")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"    ⚠  Cannot read {jf.name}: {e}")
            except json.JSONDecodeError as e:
                logger.warning(f"    ⚠  Invalid JSON in {jf.name}: {e}")

    if combined:
        try:
            merged_json.write_text(
                json.dumps(combined, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"    ✓ JSON → {merged_json.name}  ({json_count} files merged)")
            return json_count
        except (OSError, PermissionError) as e:
            logger.error(f"    ✗ Failed to write {merged_json.name}: {e}")
            return 0
    else:
        logger.warning(f"    ⚠  No .json files found for {stem}")
        return 0


def _save_merge_info(
    stem: str,
    out: Path,
    chunk_count: int,
    md_count: int,
    json_count: int,
) -> None:
    """Save merge metadata for auditing/debugging."""
    info_file = out / f"{stem}_merged_info.json"
    
    info = {
        "source_stem": stem,
        "chunks_count": chunk_count,
        "md_files_merged": md_count,
        "json_files_merged": json_count,
    }
    
    try:
        info_file.write_text(json.dumps(info, indent=2), encoding="utf-8")
        logger.debug(f"    ✓ Merge info saved: {info_file.name}")
    except (OSError, PermissionError) as e:
        logger.warning(f"    ⚠  Could not save merge info: {e}")
