# invoice-ocr

Invoice field extraction pipeline (synthetic portfolio repository).

## Stack

- Python
- OCR
- PyTorch
- computer vision

## Setup

```bash
make install
make test
```

## Architecture

The service fine-tuned a layout-aware extraction model and wrapped it in a pipeline that routes low-confidence fields to a human. See `src/` for the pipeline entry points.
