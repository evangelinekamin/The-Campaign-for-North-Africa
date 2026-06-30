"""Batch OCR every page image with baidu/Unlimited-OCR.

Resumable: a page whose output .md already exists is skipped, so the run can be
killed and restarted without losing work. One PROGRESS line per page is printed
to stdout for live monitoring; failures are written as an error-banner .md so the
final concatenation stays complete and the page is not retried endlessly.

Inference is GPU-bound and serial (single model, single GPU). Page rasterisation
was already parallelised upstream; here the GPU is the bottleneck by nature.
"""
import sys
import glob
import os
import time
import traceback
import warnings
import torch
from PIL import Image
from transformers import AutoModel, AutoTokenizer
from transformers.utils import logging as hf_logging

warnings.filterwarnings("ignore")
hf_logging.set_verbosity_error()  # silence the per-page pad/attention-mask warnings

Image.MAX_IMAGE_PIXELS = None  # the foldout charts exceed Pillow's default bomb guard

MODEL_DIR = sys.argv[1]
PAGES_DIR = sys.argv[2]
OUT_DIR = sys.argv[3]
PROMPT = sys.argv[4] if len(sys.argv) > 4 else "<image>document parsing."
# Cap generation length. Dense foldout charts otherwise loop to the token limit
# producing tens of thousands of garbage chars; a small cap grabs the title fast.
MAX_LEN = int(sys.argv[5]) if len(sys.argv) > 5 else 32768

# Oversized foldout charts get downscaled to this long side before inference. The
# model's Gundam tiling internally caps effective resolution near this anyway, so
# this bounds compute/VRAM with no real fidelity loss while avoiding 70MP edge cases.
MAX_SIDE = 3400

os.makedirs(OUT_DIR, exist_ok=True)
SCRATCH_INFER = os.path.join(OUT_DIR, "_infer_tmp")  # model's own save dir (unused output)
RESIZED_DIR = os.path.join(OUT_DIR, "_resized")
os.makedirs(RESIZED_DIR, exist_ok=True)


def prepare_image(page):
    """Return a path to feed the model, downscaling oversized pages. Returns
    (path, note) where note flags downscaled chart pages for the output banner."""
    with Image.open(page) as im:
        w, h = im.size
        if max(w, h) <= MAX_SIDE:
            return page, ""
        scale = MAX_SIDE / max(w, h)
        new = (max(1, round(w * scale)), max(1, round(h * scale)))
        small = im.convert("RGB").resize(new, Image.LANCZOS)
    out = os.path.join(RESIZED_DIR, os.path.basename(page))
    small.save(out)
    return out, f"oversized {w}x{h} -> {new[0]}x{new[1]}"

pages = sorted(glob.glob(os.path.join(PAGES_DIR, "page-*.png")))
total = len(pages)
print(f"[init] pages={total} prompt={PROMPT!r}", flush=True)
print(f"[init] torch {torch.__version__} cuda={torch.cuda.is_available()}", flush=True)

t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_DIR,
    trust_remote_code=True,
    use_safetensors=True,
    torch_dtype=torch.bfloat16,
).eval().cuda()
print(f"[load] model ready in {time.time()-t0:.1f}s", flush=True)


def page_num(path):
    base = os.path.basename(path)
    return base.replace("page-", "").replace(".png", "")


done = skipped = failed = 0
for i, page in enumerate(pages, 1):
    num = page_num(page)
    out_md = os.path.join(OUT_DIR, f"page-{num}.md")
    if os.path.exists(out_md) and os.path.getsize(out_md) > 0:
        skipped += 1
        print(f"PROGRESS page={num} idx={i}/{total} SKIP (exists)", flush=True)
        continue
    t1 = time.time()
    try:
        feed, note = prepare_image(page)
        result = model.infer(
            tokenizer,
            prompt=PROMPT,
            image_file=feed,
            output_path=SCRATCH_INFER,
            base_size=1024, image_size=640, crop_mode=True,
            max_length=MAX_LEN,
            no_repeat_ngram_size=35, ngram_window=128,
            eval_mode=True,
            save_results=False,
        )
        text = result if isinstance(result, str) else (
            result[0] if isinstance(result, (list, tuple)) and result else "")
        banner = f"<!-- large foldout chart, {note}; OCR best-effort -->\n\n" if note else ""
        with open(out_md, "w") as f:
            f.write(banner + text)
        done += 1
        print(f"PROGRESS page={num} idx={i}/{total} OK chars={len(text)} "
              f"secs={time.time()-t1:.1f}{' [downscaled]' if note else ''}", flush=True)
    except Exception as e:  # noqa: BLE001 - one bad page must not kill the run
        failed += 1
        with open(out_md, "w") as f:
            f.write(f"<!-- OCR FAILED for page {num}: {e} -->\n")
        print(f"PROGRESS page={num} idx={i}/{total} FAIL {e}", flush=True)
        traceback.print_exc()
    if i % 5 == 0:
        torch.cuda.empty_cache()

print(f"[done] ok={done} skipped={skipped} failed={failed} "
      f"total_secs={time.time()-t0:.1f}", flush=True)
