"""The real hub island, wave 13: the avenue at cand-1's angle. Three pro rolls.

Wave 12's lesson: the word "straight" plus a second composition reference produced a frontal
symmetric view ("this is straight angle, not isometric" — rejected 0%). Corrections: cand-1
is the ONLY reference (the H echo also spawned wave12-L's floating heads); the viewpoint is
demanded twice, in the usage note and in the description itself (corner-facing three-quarter
isometric); the avenue CLIMBS the terraces diagonally instead of running "straight"; golden
hour leads the description instead of trailing it.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave13")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art island drenched in warm amber golden-hour sunset light, viewed "
    "from a three-quarter isometric angle with the island's corner facing the viewer, one "
    "island filling the entire frame: a smooth clean volcano cone with a quiet crater at "
    "the back, its slopes carpeted in low green moss and undergrowth, two colossal carved "
    "stone panther heads flanking the volcano with jaws gaping open and white waterfalls "
    "pouring from their mouths toward the town, one large prominent dark tunnel portal at "
    "the volcano's base framed in carved stone, clearly leading deep into the mountain, a "
    "wide open paved way climbing the terraces diagonally from the harbor quay up to the "
    "tunnel portal, the whole approach completely clear, a walled stone citadel of varied "
    "terracotta-roofed houses and small shopfronts lining the sides of the terraces, every "
    "street stair and plaza wide open and clearly unobstructed, a few small barrels tucked "
    "against walls, one single long wooden dock jutting from the stone quay into the "
    "harbor, the harbor water open glassy and empty, a lighthouse on a curled breakwater "
    "arm, a small sandy beach cove on one side, the whole town silent and deserted under "
    "still clear air, long warm shadows, rich amber and teal palette, clean hand-painted "
    "pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([13131, 13242, 13353]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(CAND1, "REPRODUCE THIS EXACT CAMERA: the three-quarter isometric angle "
                           "and projection of this image, its warm golden-hour palette and "
                           "atmosphere, its stone material and terraced citadel massing"),
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
                    p = os.path.join(OUT, f"cand-{chr(77 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave13 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
