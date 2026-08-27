"""The real hub island, wave 10: three pro rolls with Ash's wave9 corrections baked in.

Wave 9 verdicts (2026-08-16): all three rejected. B closest to cand1. The corrections, his
words distilled: ONE tunnel only; two panther heads with waterfalls stay; the EXACT cand1
camera angle (C drifted); cand1 atmosphere; CLEAR walkability — houses, shops, a few small
barrels fine, but streets and plazas must be open and unobstructed, nothing overlapping the
walking ground; foliage as carpet, never discrete trees (they arrive as assets); volcanos
came out glitched, so the cone is described plainly and simply.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave10")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art volcanic harbor island at golden hour, one island filling the "
    "entire frame: a smooth clean volcano cone with a quiet crater at the north, its slopes "
    "carpeted in low green moss and undergrowth, two colossal carved stone panther heads "
    "flanking the volcano with jaws gaping open and white waterfalls pouring from their "
    "mouths toward the town, a walled stone citadel of varied terracotta-roofed houses and "
    "small shopfronts on three terraces stepping down to a stone harbor, every street stair "
    "and plaza wide open and clearly unobstructed, a few small barrels tucked against walls, "
    "one single dark arched tunnel gate set into the upper terrace wall, a long stone quay "
    "with a lighthouse on a curled breakwater arm, a small sandy beach cove, the whole town "
    "silent and deserted, warm low golden sunset light, long soft shadows, rich amber and "
    "teal palette, clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([10111, 10222, 10333]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(CAND1, "the EXACT isometric camera angle and projection of this image, "
                           "its palette, golden-hour atmosphere, stone material, terraced "
                           "citadel massing and harbor layout"),
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
                    p = os.path.join(OUT, f"cand-{chr(68 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave10 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
