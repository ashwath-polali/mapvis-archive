"""Wave 20: nprime-2's twin, its four flaws fixed at birth. Three pro rolls.

The owner's base choice (2026-08-16): wave14 nprime-2 — right angle, right style, warm
daylight. Its four flaws: a house blocking the central staircase, a second tunnel in the
quay wall, duplicated waterfall channel-runs, and a too-empty plaza. Surgery fixes the first
three on the original in parallel; this wave rolls a twin with all four fixed at birth.
nprime-2 is the SOLE reference (its daylight, angle and composition are accepted). No dusk,
no night, ever again. NOT front-facing: nprime-2's own three-quarter view carries.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave20")
os.makedirs(OUT, exist_ok=True)

NPRIME2 = os.path.join(HERE, "wave14", "nprime-2_0.png")

DESCRIPTION = (
    "isometric pixel art island in warm late-afternoon golden light, viewed from a "
    "three-quarter isometric angle with the island's corner facing the viewer, one island "
    "filling the entire frame: a smooth clean volcano cone with a quiet crater at the "
    "back, its slopes carpeted in low green moss and undergrowth, two colossal carved "
    "stone panther heads emerging from the volcano's slopes with jaws gaping open, one "
    "single white waterfall pouring from each mouth straight down the rock into mist, one "
    "single great dark stone portal at the volcano's base, the only doorway on the whole "
    "island, clearly leading deep inside, the grand staircase descending from the portal "
    "to the plaza completely clear with open flagstone on both sides, a walled stone "
    "citadel of varied terracotta-roofed houses and small shopfronts set along the outer "
    "sides of the terraces well away from the staircase, the plaza edges dressed with "
    "market stalls under striped awnings and small crates and barrels against the walls "
    "while the plaza centre stays wide open, unbroken solid stone quay walls, one single "
    "long wooden dock jutting from the stone quay into the harbor, the harbor water open "
    "glassy and empty, a lighthouse on a curled breakwater arm, a small sandy beach cove "
    "under a grassy headland, the whole town silent and deserted under still clear air, "
    "long warm shadows, rich amber and teal palette, clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([20201, 20302, 20403]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(NPRIME2, "REPRODUCE THIS EXACT ISLAND: its camera angle, warm daylight "
                            "palette, composition, heads, portal, terraces, harbor and "
                            "beach — with the staircase completely clear, one single "
                            "doorway, one clean fall per panther mouth, and market stalls "
                            "dressing the plaza edges"),
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
                    p = os.path.join(OUT, f"twin-{i + 1}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave20 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
