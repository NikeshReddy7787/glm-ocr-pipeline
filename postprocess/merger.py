"""
postprocess/merger.py

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
        apple_10K__chunk001_.../   (originals kept for reference)
"""

import json
from pathlib import Path


def merge(output_dir: str, source_stems: set[str]) -> None:
    """
    For every source PDF stem, find all its chunk sub-folders,
    sort them by chunk number, and concatenate their .md / .json outputs.
    """
    out = Path(output_dir)

    print(f"\n{'─'*55}")
    print(f"🔗  Merging chunk outputs")
    print(f"{'─'*55}")

    for stem in sorted(source_stems):
        # Find all subdirs that belong to this source PDF
        # They are named  <stem>__chunk*
        chunk_dirs = sorted(out.glob(f"{stem}__chunk*"))

        if not chunk_dirs:
            # PDF wasn't chunked — nothing to merge
            continue

        print(f"\n  📄 {stem}  ({len(chunk_dirs)} chunks)")

        _merge_markdown(stem, chunk_dirs, out)
        _merge_json(stem, chunk_dirs, out)


def _merge_markdown(stem: str, chunk_dirs: list[Path], out: Path) -> None:
    merged_md   = out / f"{stem}_merged.md"
    parts       = []

    for chunk_dir in chunk_dirs:
        md_files = sorted(chunk_dir.glob("*.md"))
        for md in md_files:
            parts.append(md.read_text(encoding="utf-8"))

    if parts:
        merged_md.write_text("\n\n".join(parts), encoding="utf-8")
        print(f"    ✅  MD  → {merged_md.name}")
    else:
        print(f"    ⚠   No .md files found for {stem}")


def _merge_json(stem: str, chunk_dirs: list[Path], out: Path) -> None:
    merged_json = out / f"{stem}_merged.json"
    combined    = []

    for chunk_dir in chunk_dirs:
        json_files = sorted(chunk_dir.glob("*.json"))
        for jf in json_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                # data may be a dict or list — wrap in a labelled entry
                combined.append({
                    "chunk": chunk_dir.name,
                    "data":  data,
                })
            except json.JSONDecodeError:
                print(f"    ⚠   Could not parse {jf.name}")

    if combined:
        merged_json.write_text(
            json.dumps(combined, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"    ✅  JSON → {merged_json.name}")
    else:
        print(f"    ⚠   No .json files found for {stem}")
