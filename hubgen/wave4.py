"""Hub-island wave 4: ONE corrected pro roll off Ash's feedback on wave3 (2026-08-14).

His notes on wave3/pro-1_0: smoke should not be baked (animate it later), trees should not be
baked (add as animated assets later), design/emptiness is right, quality question handled
separately by 1:1 display scaling. So: same design language, anchored on pro-1_0 itself as the
composition reference, description rewritten to a quiet bare-slope island. Wave3 stays intact
as the fallback candidate.

One call, then look. No chain-rolling.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave4")
os.makedirs(OUT, exist_ok=True)

ANCHOR = os.path.join(HERE, "wave3", "pro-1_0.png")

DESCRIPTION = (
    "isometric pixel art island seen from above, one volcanic island filling the frame: a quiet "
    "dormant volcano crater at the north, its slopes bare grass and dark volcanic rock, a walled "
    "stone harbor town of small houses with terracotta roofs built on three flat terraces "
    "stepping down to the sea, wide open flagstone plazas between the houses, broad stone "
    "staircases linking the terraces, a dark arched tunnel mouth set into the upper terrace "
    "wall, a long stone quay with a lighthouse on a breakwater arm, a small sandy beach cove, "
    "streets and plazas empty and open with clear walkable ground, warm golden afternoon light "
    "from the upper left, clean hand-painted pixel art"
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
            ref(ANCHOR, "island composition, terraced town massing, empty plazas and warm palette"),
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
                p = os.path.join(OUT, f"pro-2_{i}.png")
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
