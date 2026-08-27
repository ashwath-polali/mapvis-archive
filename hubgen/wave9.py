"""The real hub island, wave 9: THREE parallel pro rolls, Ash picks from a set.

Wave 8 rejected outright ("worst hub island, almost comical"). Changes by his order
(2026-08-16): colossal gaping panther heads embedded in the volcano with waterfalls pouring
from their mouths; absolutely nothing living or asset-like (houses and static things fine);
rest is cand-1: golden hour stone harbor island. Recipe changes: the genre word "port town"
is dropped (it summoned sailors and boats), the emptiness is stated harder but still with
zero negations, and the invented flourish lists are gone so the cand1 reference carries the
look. Three seeds in parallel because one-shot rolls keep dying on his eye.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave9")
os.makedirs(OUT, exist_ok=True)

CAND1 = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"

DESCRIPTION = (
    "isometric pixel art volcanic harbor island at golden hour, one island filling the "
    "entire frame: a volcano at the north wrapped in dense green foliage, two colossal "
    "carved stone panther heads embedded in the volcano's slopes with jaws gaping open and "
    "white waterfalls pouring from their mouths down toward the town, a walled stone citadel "
    "of varied terracotta-roofed houses on three terraces stepping down to a stone harbor, "
    "wide flagstone plazas and grand staircases, a dark arched tunnel gate in the upper "
    "wall, a long stone quay with a lighthouse on a curled breakwater arm, a small sandy "
    "beach cove, the whole town silent and deserted, every street stair and dock completely "
    "bare, warm low golden sunset light, long soft shadows, rich amber and teal palette, "
    "clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([9101, 9202, 9303]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(CAND1, "palette, golden-hour light, stone material, terraced citadel "
                           "massing, and the harbor and dock layout"),
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
                    p = os.path.join(OUT, f"cand-{chr(65 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave9 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
