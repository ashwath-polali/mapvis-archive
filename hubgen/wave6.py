"""Cand-1 exact husk, the full-size pro roll (688x384, ~40 gens, ONE call).

Wave5 split the problem: init strength 150 kept cand-1 but kept its trees/smoke too; strength
80 emptied it but drifted material. Pro's labeled references carry the two halves separately:
cand1-ref = identity (layout, stone, palette, light), cand1-empty-v3 = emptiness (bare
terraces, nothing built). Description names only what the empty state contains.

One call, then look. No chain-rolling.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave6")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"
EMPTY = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\cand1-empty-v3.png"

DESCRIPTION = (
    "isometric pixel art volcanic island, an empty uninhabited stage: a quiet volcano with "
    "bare grass and dark rock slopes under a clear sky, wide empty stone terraces with low "
    "walls stepping down to the sea, broad bare staircases linking the terraces, a dark arched "
    "tunnel mouth in the upper terrace wall, an empty stone quay with a lighthouse on a "
    "breakwater arm, a sandy beach cove, every plaza and street bare flat flagstone, warm "
    "golden afternoon light from the upper left, clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    body = {
        "description": DESCRIPTION,
        "image_size": {"width": 688, "height": 384},
        "no_background": True,
        "reference_images": [
            ref(CAND1, "the exact island to reproduce: its layout, terraces, quay, lighthouse, "
                       "tunnel mouth, beach, stone material, palette and light"),
            ref(EMPTY, "how empty it is: bare terraces and plazas, nothing built on them, "
                       "no trees, no smoke"),
        ],
    }
    out = pxl.post("/v2/generate-image-v2", body)
    jid = out["background_job_id"]
    print("pro job", jid, flush=True)
    t0 = time.time()
    while time.time() - t0 < 900:
        j = pxl.get("/v2/background-jobs/" + jid)
        st = (j.get("status") or "").lower()
        if st in ("completed", "success", "succeeded", "done"):
            imgs = []
            _collect(j, imgs)
            for i, b in enumerate(imgs):
                import base64
                p = os.path.join(OUT, f"husk-1_{i}.png")
                open(p, "wb").write(base64.b64decode(b))
                print("saved", p, flush=True)
            return
        if st in ("failed", "error", "cancelled"):
            print("JOB FAILED", json.dumps(j)[:500], flush=True)
            return
        time.sleep(8)
    print("TIMEOUT", jid, flush=True)


def _collect(o, acc, depth=0):
    if depth > 7:
        return
    if isinstance(o, dict):
        b = o.get("base64")
        if isinstance(b, str) and len(b) > 500:
            acc.append(b)
        else:
            for v in o.values():
                _collect(v, acc, depth + 1)
    elif isinstance(o, list):
        for v in o:
            _collect(v, acc, depth + 1)


if __name__ == "__main__":
    main()
