# glm-ocr-pipeline

GLM-OCR runner for PDF datasets. Auto-chunks large PDFs, runs OCR, merges outputs back per source file.

## Structure

```
glm-ocr-pipeline/
├── conf.yaml            ← OCR config (edit api_host / api_key here)
├── main.py              ← entry point
├── requirements.txt
├── preprocess/
│   └── chunker.py       ← discover PDFs recursively, split if > 90 pages
└── postprocess/
    └── merger.py        ← merge chunk outputs into one file per source PDF
```

## Kaggle

```python
# Cell 1
!pip install -q pypdf glmocr

# Cell 2
!git clone https://github.com/YOUR_USERNAME/glm-ocr-pipeline.git
%cd glm-ocr-pipeline

# Cell 3 — edit conf.yaml if needed (api_host, api_key)

# Cell 4
!python main.py /kaggle/input/10K10Q --output /kaggle/working/ocr_results
```

## Output

```
ocr_results/
  apple_10K__chunk001_p0001-p0090/   ← raw chunk output
  apple_10K__chunk002_p0091-p0180/
  apple_10K_merged.md                ← all pages merged in order ✅
  apple_10K_merged.json
  google_10Q/                        ← small PDF, no chunking
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `./ocr_results` | Where to write results |
| `--no-save` | off | Print only, no files |
| `--keep-chunks` | off | Don't delete temp split PDFs |
