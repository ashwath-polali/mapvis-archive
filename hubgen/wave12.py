"""The real hub island, wave 12: the processional avenue. Three pro rolls.

Ash on wave11 (2026-08-16): H is the pick of the litter, but two stands and possibly a house
block the tunnel approach, chimney wisps leaked, and the path to the tunnel needs to be a
first-class feature, not leftover space. This wave makes the avenue itself part of the
architecture: a broad open processional way from the harbor to the portal, buildings lining
the SIDES. Smoke suppressed at the source concept: still air, quiet rooftops, nothing burning
anywhere. References: cand1 for angle/palette/atmosphere, cand-H for heads and composition.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave12")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"
CANDH = os.path.join(HERE, "wave11", "cand-H_0.png")

DESCRIPTION = (
    "isometric pixel art volcanic harbor island at golden hour, one island filling the "
    "entire frame: a smooth clean volcano cone with a quiet crater at the north, its slopes "
    "carpeted in low green moss and undergrowth, two colossal carved stone panther heads "
    "flanking the volcano with jaws gaping open and white waterfalls pouring from their "
    "mouths toward the town, one large prominent dark tunnel portal at the volcano's base "
    "framed in carved stone, clearly leading deep into the mountain, a broad open "
    "processional avenue running straight from the harbor plaza up the grand staircases to "
    "the tunnel portal, the whole approach completely clear and open, a walled stone citadel "
    "of varied terracotta-roofed houses and small shopfronts lining the SIDES of the "
    "terraces, every street stair and plaza wide open and clearly unobstructed, a few small "
    "barrels tucked against walls, one single long wooden dock jutting from the stone quay "
    "into the harbor, the harbor water open glassy and empty, a lighthouse on a curled "
    "breakwater arm, a small sandy beach cove, the whole town silent and deserted under "
    "still clear air, warm low golden sunset light, long soft shadows, rich amber and teal "
    "palette, clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([12121, 12232, 12343]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(CAND1, "the EXACT isometric camera angle and projection, palette, "
                           "golden-hour atmosphere, stone material and terraced massing"),
                ref(CANDH, "the flanking panther heads and the overall island composition, "
                           "with the tunnel approach left completely open"),
            ],
        }
        out = pxl.post("/v2/generate-image-v2", body)
        jobs.append((i, out["background_job_id"]))
        print("submitted", i, out["background_job_id"], flush=True)
    t0 = time.time()
    done = set()
    while time.time() - t0 < 1200 and len(done) < len(jobs):
        for i, jid in jobs:
            if i in done:
                continue
            j = pxl.get("/v2/background-jobs/" + jid)
            st = (j.get("status") or "").lower()
            if st in ("completed", "success", "succeeded", "done"):
                imgs = []
                _collect(j, imgs)
                for k, b in enumerate(imgs):
                    import base64
                    p = os.path.join(OUT, f"cand-{chr(74 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave12 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
