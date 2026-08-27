"""Wave 18: LOCKED. The final rule set, three rolls, graded before showing.

Ash, final form (2026-08-16): like cand1 or better; ONE prominent tunnel in the volcano and
none anywhere else (no harbor arches); two panther heads with PROPER waterfalls pouring from
their mouths; cand1 angle and atmosphere; a dock; walkability across the entire island;
nothing blocking the tunnel (no house near it); no trees; no smoke. Anchor: wave17 strict-Q
(passed every rule except its beach palms), falls restored in words, cove stated bare.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave18")
os.makedirs(OUT, exist_ok=True)

ANCHOR = os.path.join(HERE, "wave17", "strict-Q_0.png")

DESCRIPTION = (
    "isometric pixel art island drenched in warm amber golden-hour sunset light, viewed "
    "from a three-quarter isometric angle with the island's corner facing the viewer, one "
    "island filling the entire frame: a smooth clean volcano cone with a quiet crater at "
    "the back, its slopes carpeted in low green moss and undergrowth, two colossal carved "
    "stone panther heads emerging from the volcano's slopes with jaws gaping open and "
    "proper white waterfalls pouring from both mouths down into stone channels, one single "
    "great dark stone portal at the volcano's base, the only doorway on the whole island, "
    "clearly leading deep inside, wide open ground all around the portal, unbroken solid "
    "stone terrace walls everywhere else, the grand staircase and paved way rising "
    "completely clear from the harbor plaza to the portal with open ground on both sides, "
    "a walled stone citadel of varied terracotta-roofed houses and small shopfronts lining "
    "only the sides of the terraces, one market stall with a striped awning in the central "
    "plaza off to one side of the way, small crates and barrels set tight against walls "
    "and quay edges with the walkways beside them open, one single long wooden dock "
    "jutting from the stone quay into the harbor, the harbor water open glassy and empty, "
    "a lighthouse on a curled breakwater arm, a bare empty sandy cove under a bare grassy "
    "headland, the whole town silent and deserted under still clear air, long warm "
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
    for i, seed in enumerate([18181, 18292, 18303]):
        body = {
            "description": DESCRIPTION,
            "image_size": {"width": 688, "height": 384},
            "no_background": True,
            "seed": seed,
            "reference_images": [
                ref(ANCHOR, "REPRODUCE THIS ISLAND'S STRUCTURE: camera angle, composition, "
                            "clear central way to the single portal, terraces, harbor and "
                            "dock — with its beach bare and waterfalls added from the two "
                            "panther mouths"),
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
                    p = os.path.join(OUT, f"lock-{chr(83 + i)}_{k}.png")
                    open(p, "wb").write(base64.b64decode(b))
                    print("saved", p, flush=True)
                done.add(i)
            elif st in ("failed", "error", "cancelled"):
                print("JOB FAILED", i, json.dumps(j)[:300], flush=True)
                done.add(i)
        time.sleep(10)
    print(f"wave18 complete: {len(done)}/{len(jobs)} jobs finished", flush=True)


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
