"""High-fidelity re-OCR of the few dense chart pages that failed the first pass.

Root cause (confirmed by eye): these pages are printed SIDEWAYS (landscape charts
on a portrait page), so the first pass OCR'd a rotated grid and produced garbled
tables. Fix: rotate the page upright and re-OCR. Orientation is unknown per page,
so we try both 90-degree rotations and keep whichever yields the best-scoring
table. If a full-page pass still fails, we tile the rotated page into top/bottom
halves and OCR each (less content per call = far less repetition risk).

The winning raw OCR overwrites out/page-NNN.md so the normal assembly picks it up
as the single source of truth.
"""
import sys
import os
import warnings
import torch
from PIL import Image
from transformers import AutoModel, AutoTokenizer
from transformers.utils import logging as hf_logging

import tables

warnings.filterwarnings("ignore")
hf_logging.set_verbosity_error()
Image.MAX_IMAGE_PIXELS = None

MODEL_DIR = sys.argv[1]
PAGES_DIR = sys.argv[2]
OUT_DIR = sys.argv[3]
PAGES = [p.strip() for p in sys.argv[4].split(",") if p.strip()]
WORK = os.path.join(OUT_DIR, "_rerun")
os.makedirs(WORK, exist_ok=True)

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_DIR, trust_remote_code=True, use_safetensors=True,
    torch_dtype=torch.bfloat16).eval().cuda()
print("[load] model ready", flush=True)


def ocr(image_path, max_len=16384):
    return model.infer(
        tokenizer, prompt="<image>document parsing.", image_file=image_path,
        output_path=os.path.join(WORK, "_tmp"),
        base_size=1024, image_size=640, crop_mode=True,
        max_length=max_len, no_repeat_ngram_size=30, ngram_window=64,
        eval_mode=True, save_results=False)


def table_score(text):
    """Total cell count across all GOOD tables in this OCR text (0 if none)."""
    total = 0
    for thtml in tables.TABLE_RE.findall(text):
        grid = tables.parse_grid(thtml)
        ok, m = tables.score_grid(grid)
        if ok:
            total += m["rows"] * m["cols"]
    return total


def best_rotation(src_png, page):
    im = Image.open(src_png).convert("RGB")
    candidates = {
        "cw": im.transpose(Image.ROTATE_270),   # 90 deg clockwise
        "ccw": im.transpose(Image.ROTATE_90),   # 90 deg counter-clockwise
    }
    best = ("", -1, None)
    for name, rot in candidates.items():
        path = os.path.join(WORK, f"page-{page}-{name}.png")
        rot.save(path)
        text = ocr(path)
        sc = table_score(text)
        print(f"  page {page} rot={name}: good-table-cells={sc} chars={len(text)}",
              flush=True)
        if sc > best[1]:
            best = (text, sc, candidates[name])
    return best


def tile_halves(rot_img, page):
    """Fallback: split the (already upright) image into top/bottom halves with a
    small overlap, OCR each, and concatenate. Returns combined text."""
    w, h = rot_img.size
    ov = int(h * 0.06)
    halves = {"top": (0, 0, w, h // 2 + ov), "bot": (0, h // 2 - ov, w, h)}
    parts = []
    for name, box in halves.items():
        path = os.path.join(WORK, f"page-{page}-tile-{name}.png")
        rot_img.crop(box).save(path)
        parts.append(ocr(path, max_len=12288))
        print(f"  page {page} tile={name}: chars={len(parts[-1])}", flush=True)
    return "\n".join(parts)


for page in PAGES:
    src = os.path.join(PAGES_DIR, f"page-{page}.png")
    text, score, rot_img = best_rotation(src, page)
    if score == 0 and rot_img is not None:
        print(f"  page {page}: full-page failed, trying tiled halves", flush=True)
        tiled = tile_halves(rot_img, page)
        if table_score(tiled) > 0:
            text, score = tiled, table_score(tiled)
    out_md = os.path.join(OUT_DIR, f"page-{page}.md")
    # Back up the original raw OCR once.
    bak = os.path.join(WORK, f"page-{page}.orig.md")
    if not os.path.exists(bak) and os.path.exists(out_md):
        with open(bak, "w") as f:
            f.write(open(out_md).read())
    with open(out_md, "w") as f:
        f.write(text)
    print(f"[done] page {page}: best good-table-cells={score} -> overwrote {out_md}",
          flush=True)

print("[all done]", flush=True)
