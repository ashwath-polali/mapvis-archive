"""Wave 17: STRICT. Three rolls. Every rule from every measured lesson, no lean experiments.

The rule set (Ash, final form, 2026-08-16):
cand1 angle + golden hour; two panther heads out of the volcano, jaws gaping, NO water;
QUIET crater, still air, zero smoke of any kind; ONE portal only, the only doorway in the
mountain, unbroken walls everywhere else; the way from harbor to portal completely clear,
open ground both sides, houses only on the sides; NO trees (moss carpet, bare headland);
wooden dock, stone harbor, lighthouse, glassy empty water; the life he wants KEPT: a market
stall with striped awning in the plaza off to one side, crates and barrels against walls
with walkways open; no lamps, no people, no ships.

Anchor: wave15 final-1 (the only roll that ever passed stair-clear + one-tunnel + unbroken
walls), waterfalls scoped out in the usage note. Every suppression phrase here earned its
place from a measured leak. Do not lean it down again.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave17")
os.makedirs(OUT, exist_ok=True)

ANCHOR = os.path.join(HERE, "wave15", "final-1_0.png")

DESCRIPTION = (
    "isometric pixel art island drenched in warm amber golden-hour sunset light, viewed "
    "from a three-quarter isometric angle with the island's corner facing the viewer, one "
    "island filling the entire frame: a smooth clean volcano cone with a quiet crater at "
    "the back, its slopes carpeted in low green moss and undergrowth, two colossal carved "
    "stone panther heads emerging dry from the volcano's slopes with jaws gaping open, one "
    "single great dark stone portal at the volcano's base, the only doorway in the "
    "mountain, clearly leading deep inside, unbroken solid stone terrace walls everywhere "
    "else, the grand staircase and paved way rising completely clear from the harbor plaza "
    "to the portal with open ground on both sides, a walled stone citadel of varied "
    "terracotta-roofed houses and small shopfronts lining only the sides of the terraces, "
    "one market stall with a striped awning standing in the central plaza off to one side "
    "of the way, small crates and barrels set tight against walls and quay edges with the "
    "walkways beside them open, one single long wooden dock jutting from the stone quay "
    "into the harbor, the harbor water open glassy and empty, a lighthouse on a curled "
    "breakwater arm, a bare grassy headland of moss and low undergrowth over a small sandy "
    "beach cove, the whole town silent and deserted under still clear air, long warm "
    "shadows, rich amber and teal palette, clean hand-painted pixel art"
)


def ref(path, usage):
    from PIL import Image
    im = Image.open(path)
    return {"image": {"type": "base64", "base64": pxl.b64_file(path)},
            "size": {"width": im.size[0], "height": im.size[1]},
            "usage_description": usage}


def main():
    jobs = []
    for i, seed in enumerate([17171, 17282, 17393]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(ANCHOR, "REPRODUCE THIS ISLAND'S STRUCTURE: camera angle, composition, "
                            "the clear central staircase to the single portal, terraces and "
                            "harbor — with dry stone where its waterfalls were, and its "
                            "crater quiet"),
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
                    p = os.path.join(OUT, f"strict-{chr(80 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave17 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
