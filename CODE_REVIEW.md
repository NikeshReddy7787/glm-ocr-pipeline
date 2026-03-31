# GLM-OCR Pipeline — Code Review & Reliability Assessment

## ✅ Strengths

1. **Clear Architecture** — Well-separated concerns: preprocess → OCR → postprocess
2. **Intelligent Chunking** — Automatically splits large PDFs (>90 pages) to respect 100-page limit
3. **Source Tracking** — Maintains `source_stem` to correctly merge chunks back to original PDF
4. **Flexible Output** — Supports `--no-save` and `--keep-chunks` options
5. **Performance Monitoring** — Tracks elapsed time per file and average metrics
6. **Recursive PDF Discovery** — Finds PDFs at any depth in directory tree

---

## ⚠️ Issues & Reliability Concerns

### **CRITICAL**

| Issue | Impact | Fix |
|-------|--------|-----|
| **No 50 MB size validation** | Large files could exceed API limits | Add file size check before processing |
| **Unvalidated input path** | Crashes if dataset path doesn't exist | Validate path exists & is readable |
| **No input sanitization** | Path traversal or invalid chars could break | Normalize and validate all paths |
| **Silent PDF read failures** | Corrupted PDFs are skipped without detail | Log detailed error reasons |
| **API connection not tested** | Pipeline fails mid-run if API unreachable | Test connection at startup |

### **HIGH**

| Issue | Impact | Fix |
|-------|--------|-----|
| **Hardcoded chunk directory** | `./pdf_chunks` can conflict | Make `CHUNKS_TMP_DIR` configurable |
| **No logging framework** | Print statements mix with errors, not searchable | Use Python `logging` module |
| **Missing output dir creation** | Might fail if output parent path invalid | Add `mkdir -p` logic or catch exception |
| **Merge depends on chunk naming** | If naming format changes, merge breaks | Add explicit chunk metadata file |
| **No retry/resume logic** | File failure = start over | Implement checkpoint system |

### **MEDIUM**

| Issue | Impact | Fix |
|-------|--------|-----|
| **GlmOcr context manager error** | If exception in loop, context may not close properly | Add error handling around context |
| **Empty queue handling** | Message says "nothing to process" but no detail | Show why queue is empty (no PDFs found vs. all invalid) |
| **JSON merge overwrites** | If two chunks have same JSON filename, second overwrites | Namespace JSON files by chunk or use array |
| **No disk space check** | Could run out of space mid-process | Check free space before chunking |

---

## 🔧 Recommended Improvements

### 1. **Add File Size Validation**
```python
# In chunker.py
CHUNK_SIZE = 90
MAX_PDF_SIZE_MB = 50

def validate_pdf(pdf: Path) -> bool:
    size_mb = pdf.stat().st_size / (1024 * 1024)
    if size_mb > MAX_PDF_SIZE_MB:
        print(f"  ⚠  SKIP {pdf.name} — {size_mb:.1f}MB exceeds {MAX_PDF_SIZE_MB}MB limit")
        return False
    return True
```

### 2. **Input Path Validation**
```python
# In main.py
def validate_dataset_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        print(f"❌ Dataset path does not exist: {path}")
        sys.exit(1)
    if not path.is_dir():
        print(f"❌ Dataset path is not a directory: {path}")
        sys.exit(1)
    return path
```

### 3. **Make Temp Directory Configurable**
```python
# In chunker.py
def build_queue(
    pdfs: list[Path],
    chunk_size: int = CHUNK_SIZE,
    tmp_dir: str = None,  # Allow None
) -> list[tuple[Path, str]]:
    if tmp_dir is None:
        tmp_dir = CHUNKS_TMP_DIR
    # ... rest of function
```

### 4. **Add Proper Logging**
```python
# New: logging_config.py
import logging
import sys

def setup_logging(level=logging.DEBUG):
    logger = logging.getLogger("glm_ocr_pipeline")
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger
```

### 5. **Better Error Tracking**
```python
# In main.py
failed_pdfs = []
for i, (pdf_path, source_stem) in enumerate(queue, 1):
    try:
        # ... processing
    except Exception as e:
        failed_pdfs.append((pdf_path.name, str(e)))
        logger.error(f"Failed to process {pdf_path}: {e}")

# At end, show summary
if failed_pdfs:
    print(f"\n⚠️  {len(failed_pdfs)} file(s) failed:")
    for name, error in failed_pdfs:
        print(f"   - {name}: {error}")
```

### 6. **Add Checkpoint/Metadata System**
```python
# Save processing state to avoid re-chunking
CHUNK_METADATA_FILE = ".chunk_metadata.json"

# After building queue, save it
with open(CHUNK_METADATA_FILE, "w") as f:
    json.dump([
        {"source": stem, "chunk": str(chunk), "timestamp": time.time()}
        for chunk, stem in queue
    ], f, indent=2)
```

---

## 📋 Testing Checklist

- [ ] Test with 0 PDFs (empty directory)
- [ ] Test with PDF >50MB (should skip with warning)
- [ ] Test with corrupted/invalid PDF file
- [ ] Test with very long filenames (>255 chars)
- [ ] Test with PDF containing special characters in name
- [ ] Test with insufficient disk space (chunk creation fails)
- [ ] Test with API unreachable (connection timeout)
- [ ] Test with permission denied on output directory
- [ ] Test with single small PDF
- [ ] Test with single large PDF requiring chunking
- [ ] Test with multiple PDFs mixed sizes
- [ ] Test with and without `--keep-chunks` flag
- [ ] Test with and without `--no-save` flag

---

## 🚀 Current Workflow

```
User runs:  python main.py /path/to/pdfs [options]
                     ↓
discover_pdfs()  → Scan & list all PDFs recursively
                     ↓
build_queue()    → Check page counts, chunk if >90 pages
                     ↓
GlmOcr.parse()   → Process each file/chunk with OCR API
                     ↓
result.save()    → Write MD + JSON to output subdirs
                     ↓
merge()          → Group chunks by source PDF stem
                     ↓
cleanup()        → Remove temp chunk PDFs (if --keep-chunks not set)
```

---

## 💾 What You Need to Implement

1. ✅ **Size validation** — Check 50 MB limit before processing
2. ✅ **Path validation** — Validate dataset path at startup
3. ✅ **Better error messages** — Show why PDFs are skipped
4. ✅ **Logging** — Replace print statements with logging module
5. ✅ **Configuration** — Move hardcoded values to config or CLI args
6. ✅ **API health check** — Test connection before processing queue
7. ✅ **Progress tracking** — Save checkpoint to resume if interrupted

---

## Code Quality Score

| Category | Score | Notes |
|----------|-------|-------|
| **Architecture** | 8/10 | Clean separation of concerns |
| **Error Handling** | 4/10 | Minimal; mostly silent failures |
| **Reliability** | 5/10 | Works for happy path, fragile for edge cases |
| **Testing** | 2/10 | No test suite |
| **Logging** | 2/10 | Only print statements |
| **Documentation** | 7/10 | Good docstrings and usage examples |
| **Performance** | 8/10 | Efficient chunking + async parallelization possibilities |

**Overall: 5.4/10** — Production-ready for basic use, needs hardening for robustness.
