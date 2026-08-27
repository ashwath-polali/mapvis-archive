"""The real hub island, wave 15: the final corrections on the nprime line. Two pro rolls.

Ash on nprime (2026-08-16): trees fix good. Remaining: the last house still crowds the
staircase to the main tunnel; a second tunnel appeared (only ONE, the great portal); he
dislikes the extra waterfall; the bottom clutter STAYS (crates and barrels are fine) as long
as walkways are open. This wave: nprime-1 as the sole reference, the corrections stated as
the world's own facts — the only doorway in the mountain, the only waterfalls pour from the
two panther mouths, the staircase rises completely clear, clutter sits tight against walls.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave15")
os.makedirs(OUT, exist_ok=True)

NPRIME = os.path.join(HERE, "wave14", "nprime-1_0.png")

DESCRIPTION = (
    "isometric pixel art island drenched in warm amber golden-hour sunset light, viewed "
    "from a three-quarter isometric angle with the island's corner facing the viewer, one "
    "island filling the entire frame: a smooth clean volcano cone with a quiet crater at "
    "the back, its slopes carpeted in low green moss and undergrowth, two colossal carved "
    "stone panther heads flanking the volcano with jaws gaping open, the island's only "
    "waterfalls pouring white from the two panther mouths toward the town, one single "
    "great dark tunnel portal at the volcano's base framed in carved stone, the only "
    "doorway in the mountain, clearly leading deep inside, the grand staircase rising "
    "completely clear from the open central plaza to the portal with open ground on both "
    "sides, unbroken solid stone terrace walls, a walled citadel of varied "
    "terracotta-roofed houses and small shopfronts lining only the sides of the terraces, "
    "every street stair and plaza wide open and clearly unobstructed, small crates and "
    "barrels set tight against the quay walls with the walkways beside them open, one "
    "single long wooden dock jutting from the stone quay into the harbor, the harbor "
    "water open glassy and empty, a lighthouse on a curled breakwater arm, a bare grassy "
    "headland of moss and low undergrowth rising over a small sandy beach cove, the whole "
    "town silent and deserted under still clear air, long warm shadows, rich amber and "
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
    for i, seed in enumerate([15151, 15262]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(NPRIME, "REPRODUCE THIS EXACT ISLAND: its camera angle, composition, "
                            "palette, heads, portal, terraces and harbor — with the "
                            "staircase to the portal completely clear, one single tunnel "
                            "only, and waterfalls only from the two panther mouths"),
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
                    p = os.path.join(OUT, f"final-{i + 1}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave15 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
