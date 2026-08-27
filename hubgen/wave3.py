"""Hub-island wave 3: ONE pro-endpoint generation at the full 688x384 canvas.

The draft ladder (2026-08-14): wave 1 A/B/C found the framing (B) and proved the cand1-ref
init carries the massing (C). Wave 2 D/E/F found the formula: E = cand1-ref init strength 100
+ explicit town content. Wave 3 takes that formula to the only endpoint that does 688x384 and
transparency: /v2/generate-image-v2 (20-40 generations per call, ONE image at this size).

Pro has no init_image, so the composition anchor rides in as labelled reference images:
cand1-ref-512 for massing, the E draft for town character and palette.

Stop rule: one call, then everything (drafts + this) goes in front of Ash. No second pro call
without looking first.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave3")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"
EDRAFT = os.path.join(HERE, "wave2", "E-init-100.png")

DESCRIPTION = (
    "isometric pixel art island seen from above, one volcanic island filling the frame: smoking "
    "volcano crater at the north with lush palm jungle on its slopes, a walled stone harbor town "
    "of small houses with terracotta roofs built on three flat terraces stepping down to the sea, "
    "wide open flagstone plazas between the houses, broad stone staircases linking the terraces, "
    "a dark arched tunnel mouth set into the upper terrace wall, a long stone quay with a "
    "lighthouse on a breakwater arm, a small sandy beach cove, streets and plazas empty and open "
    "with clear walkable ground, warm golden afternoon light from the upper left, clean "
    "hand-painted pixel art"
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
            ref(CAND1, "island composition and terraced stone citadel massing"),
            ref(EDRAFT, "town character, terracotta roofs and warm palette"),
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
                p = os.path.join(OUT, f"pro-1_{i}.png")
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
