"""Wave 22: the corner-facing phrase is dead. One roll.

Found (2026-08-16): "with the island's corner facing the viewer" entered at wave 13 and rode
every roll since — it commands a symmetric corner-front composition and has been fighting
cand-1's own oblique view the whole time ("removed the little isometric shit we had"). The
angle instruction returns to wave-16's form: defer to the reference's view entirely. The
dock is described minimally so it cannot over-render. Everything else per the sealed rules.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave22")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art island in warm late-afternoon golden light with deep saturated "
    "colors, in the exact three-quarter isometric view of the reference, the dense layered "
    "town drawn large and close, one island filling the entire frame: a smooth clean "
    "volcano cone with a quiet crater at the back, its slopes carpeted in low green moss "
    "and undergrowth, two colossal carved stone panther heads emerging from the volcano's "
    "slopes with jaws gaping open and one white waterfall pouring from each mouth straight "
    "down the rock into mist, one single great dark stone portal at the volcano's base, "
    "the only doorway on the whole island, clearly leading deep inside, the grand "
    "staircase descending from the portal to the harbor plaza completely clear with open "
    "flagstone on both sides, a walled stone citadel of varied terracotta-roofed houses "
    "with warm glowing windows and small shopfronts set along the outer sides of the "
    "terraces, market stalls under striped awnings and crates and barrels dressing the "
    "plaza edges against the walls while every street stair and walkway stays wide open, "
    "unbroken solid stone quay walls, a simple straight wooden dock at the waterfront "
    "quay, the harbor water glassy and empty, a lighthouse on a curled breakwater arm, a "
    "bare sandy cove under a bare grassy headland, the whole town silent and deserted "
    "under still clear air, long warm shadows, rich amber and deep teal palette, clean "
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
        "seed": 22222,
        "reference_images": [
            ref(CAND1, "ONLY this painting's style and view: its exact camera angle and "
                       "isometric projection, warm golden atmosphere, deep saturated "
                       "palette, glowing windows, stone material and large close building "
                       "scale. Not its layout."),
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
                p = os.path.join(OUT, f"two_{k}.png")
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
