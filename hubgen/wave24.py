"""Wave 24: the hillside port. One roll.

The named gap (2026-08-16, side-by-side): cand-1 is a hillside PORT at sea level — working
quay as the spine, cargo stacked, town climbing the slope behind it. Every generated roll
was a fortress table: raised pedestal, flat top, water on a cliff rim. This wave describes
the structure as the world's own shape: quay AT SEA LEVEL, hillside sloping naturally into
the water, houses climbing stepped terraces, a stair street winding up to the single portal.
All sealed suppressions intact.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave24")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art island in warm late-afternoon golden light with deep saturated "
    "colors, in the exact three-quarter isometric view of the reference, buildings drawn "
    "large and close, one island filling the entire frame: a natural hillside island "
    "sloping gently down into the sea on every side, a working stone harbor quay running "
    "along the waterfront at sea level, stacked with cargo crates, barrels and sacks, a "
    "simple straight wooden dock reaching into the glassy empty water, a port town of a "
    "handful of varied terracotta-roofed houses with warm glowing windows climbing the "
    "hillside behind the quay on natural stepped stone terraces, a few market stalls "
    "under striped awnings along the quay, a wide stone stair street winding up from the "
    "harbor between the houses to one single great dark stone portal at the volcano's "
    "base, the only doorway on the whole island, clearly leading deep inside, above the "
    "town a smooth simple volcano cone of large calm rock faces with a quiet crater, its "
    "slopes carpeted in low green moss and undergrowth, two colossal carved stone panther "
    "heads emerging from the volcano's slopes with jaws gaping open and one white "
    "waterfall pouring from each mouth straight down the rock into mist, every street "
    "stair and walkway wide open and clear, a lighthouse on a curled breakwater arm, a "
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
        "seed": 24242,
        "reference_images": [
            ref(CAND1, "this painting's style AND its structure: a working waterfront "
                       "port at sea level with the town climbing the hillside behind it, "
                       "its exact camera angle and isometric projection, warm golden "
                       "atmosphere, deep saturated palette, glowing windows, stone "
                       "material and large close building scale"),
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
                p = os.path.join(OUT, f"port_{k}.png")
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
