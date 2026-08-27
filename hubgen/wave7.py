"""The REAL hub island, wave 7 drafts: cand1-like richness, golden hour, absence by omission.

Ash's brief (2026-08-16): hub-a2 was only ever the test island. The real one is a cand1-class
REGENERATION: stone harbor citadel with harbor and dock, many varied houses, market awnings,
the paw gate, golden-hour light — everything cand-1 has EXCEPT the things that must arrive
later as living assets: people, ships, discrete trees, smoke. His law for prompting the
absence: never name the removed thing (a negation alters how everything else is generated).
The description simply describes the world in the state where those things happen to be
absent: "empty wooden docks", "still empty streets", "quiet crater", foliage as ground cover
rather than trees. Nothing is forbidden; it is just not there.

Two drafts at 1 gen each (cand1-ref init at strengths 100 and 150), then ONE pro roll.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave7")
os.makedirs(OUT, exist_ok=True)

INIT = os.path.join(HERE, "wave1", "_init-688.png")  # cand1-ref at 400x224

DESCRIPTION = (
    "isometric pixel art volcanic island port town at golden hour, one island filling the "
    "entire frame: a quiet volcano crater wrapped in dense green foliage at the north, a "
    "walled stone citadel town on three terraces stepping down to a stone harbor, many varied "
    "terracotta-roofed stone houses with striped market awnings and hanging banners between "
    "them, wide flagstone plazas and grand staircases, a dark arched tunnel gate carved with a "
    "panther paw in the upper wall, a long stone quay with empty wooden docks and mooring "
    "posts, a lighthouse on a curled breakwater arm, crates and barrels stacked by the harbor "
    "wall, a small sandy beach cove, still empty streets in warm low sunset light, long soft "
    "shadows, rich amber and teal palette, clean hand-painted pixel art"
)


def run(name, seed, strength):
    body = {
        "description": DESCRIPTION,
        "image_size": {"width": 400, "height": 224},
        "no_background": False,
        "isometric": True,
        "text_guidance_scale": 8,
        "detail": "highly detailed",
        "shading": "detailed shading",
        "seed": seed,
        "init_image": {"type": "base64", "base64": pxl.b64_file(INIT)},
        "init_image_strength": strength,
    }
    out = pxl.post("/v1/generate-image-pixflux", body)
    p = os.path.join(OUT, name + ".png")
    pxl.save_result(out, p)
    print("saved", p, flush=True)


if __name__ == "__main__":
    run("R-init100", seed=7001, strength=100)
    run("S-init150", seed=7002, strength=150)
    print("wave7 complete: 2 generations spent", flush=True)
