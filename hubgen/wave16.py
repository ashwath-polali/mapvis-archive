"""Wave 16: fresh. One roll.

Ash (2026-08-16): stop iterating on drift, regenerate fresh. The complete spec, distilled to
its bones, nothing else: walkability; panther heads out of the volcano (no waterfalls — water
arrives later as an animated asset, which fits the asset philosophy anyway); cand1 angle and
style; stone harbor; ONE prominent tunnel clearly into the volcano; a walkable path to it; a
wooden dock; no trees; like nprime-2's emptiness. Lean prompt, single cand1 reference, one
seed. The bloated 180-word prompt salad is retired.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave16")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art island in warm golden-hour light, the exact three-quarter "
    "isometric angle of the reference, one island filling the frame: a volcano at the back "
    "with two colossal carved stone panther heads emerging from its slopes, jaws gaping "
    "open, a single great stone portal at the volcano's base leading into the mountain, a "
    "wide walkable stone way from the harbor up to the portal, a stone harbor town of "
    "terracotta-roofed houses lining the terrace sides, open plazas and streets, a wooden "
    "dock in the harbor, glassy empty water, a lighthouse on a breakwater, bare grassy "
    "slopes and a sandy cove, deserted and still, rich amber and teal palette, clean "
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
        "seed": 16161,
        "reference_images": [
            ref(CAND1, "the exact three-quarter isometric camera angle, golden-hour "
                       "palette, stone material and overall style of this island"),
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
            for k, b in enumerate(imgs):
                import base64
                p = os.path.join(OUT, f"fresh_{k}.png")
                open(p, "wb").write(base64.b64decode(b))
                print("saved", p, flush=True)
            return
        if st in ("failed", "error", "cancelled"):
            print("JOB FAILED", json.dumps(j)[:400], flush=True)
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
