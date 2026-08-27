"""The REAL hub island, wave 8: ONE pro roll at 688x384.

Wave 7's lesson, bought for 2 gens: an INIT preserves what it contains — cand-1's smoke,
trees and ships all survived both strengths. Removal only works in the reference lane, where
the description outranks the image (wave 4 proved it: quiet crater and bare slopes beat a
smoking, tree-covered reference). So: cand1-ref rides as a labeled REFERENCE for palette,
light, material, massing and harbor layout; the description carries the full cand1-class
richness with the absences stated by omission — empty docks, still streets, quiet crater,
foliage as ground cover. People, ships, discrete trees and smoke are simply never mentioned.

One call, then Ash's eye.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave8")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art volcanic island port town at golden hour, one island filling the "
    "entire frame: a quiet volcano crater wrapped in dense green foliage at the north, a "
    "walled stone citadel town on three terraces stepping down to a stone harbor, many varied "
    "terracotta-roofed stone houses with striped market awnings and hanging banners between "
    "them, wide flagstone plazas and grand staircases, a dark arched tunnel gate carved with a "
    "panther paw in the upper wall, a long stone quay with empty wooden docks and mooring "
    "posts, a lighthouse on a curled breakwater arm, crates and barrels stacked by the harbor "
    "wall, a small sandy beach cove, still empty streets in warm low sunset light, long soft "
    "shadows, rich amber and teal palette, clean hand-painted pixel art"
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
            ref(CAND1, "palette, golden-hour light, stone material, terraced citadel massing, "
                       "and the harbor and dock layout"),
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
                p = os.path.join(OUT, f"hub-real_{i}.png")
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
