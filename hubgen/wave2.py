"""Hub-island wave 2: converge the surviving direction. 3 pixflux drafts, 3 generations.

Wave-1 verdicts (looked at, 2026-08-14): A dead (flat toy fort). B's whole-island framing and
palette won but 'empty' over-triggered and erased the town. C's cand1-ref init carried the
terraced massing (tunnel, stairs, quay) but painted it muddy.

Wave 2 tests the recombination:
  D  B's framing + an explicit small town (houses named, ground kept open)
  E  cand1-ref init at strength 100 (keep more massing) + D's town description
  F  cand1-ref init at strength 60 + D's town description (the loose hybrid)

Stop rule unchanged: look at all three before any pro spend.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wave2")
os.makedirs(OUT, exist_ok=True)

INIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wave1", "_init-688.png")

PROMPT_TOWN = (
    "isometric pixel art island seen from above, one volcanic island filling the frame: smoking "
    "volcano crater at the north with lush palm jungle on its slopes, a stone harbor town of "
    "small houses with terracotta roofs built on three flat terraces stepping down to the sea, "
    "wide open flagstone plazas between the houses, broad stone staircases linking the terraces, "
    "a dark arched tunnel mouth set into the upper terrace wall, a long stone quay with a "
    "lighthouse on a breakwater arm, a small sandy beach cove, open walkable ground between all "
    "buildings, warm golden afternoon light from the upper left, clean hand-painted pixel art"
)


def run(name, description, seed, init=None, init_strength=60):
    body = {
        "description": description,
        "image_size": {"width": 400, "height": 224},
        "no_background": False,
        "isometric": True,
        "text_guidance_scale": 8,
        "detail": "highly detailed",
        "shading": "detailed shading",
        "seed": seed,
    }
    if init:
        body["init_image"] = {"type": "base64", "base64": pxl.b64_file(init)}
        body["init_image_strength"] = init_strength
    out = pxl.post("/v1/generate-image-pixflux", body)
    p = os.path.join(OUT, name + ".png")
    pxl.save_result(out, p)
    print("saved", p, flush=True)


if __name__ == "__main__":
    run("D-town-text", PROMPT_TOWN, seed=2001)
    run("E-init-100", PROMPT_TOWN, seed=2002, init=INIT, init_strength=100)
    run("F-init-60", PROMPT_TOWN, seed=2003, init=INIT, init_strength=60)
    print("wave2 complete: 3 generations spent (6 total)", flush=True)
