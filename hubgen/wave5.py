"""Cand-1 exact husk, draft ladder (2 pixflux gens at 400x224).

Ash's brief (2026-08-15): the island exactly like cand-1, but with the assets, smoke and trees
lifted out — as if the town was planned into the painting and then removed before it was built.
July's cand1-empty-v* lost the terraced structure by prompting removal. This run: cand1-ref as
the init (the island IS the input), and the description names only what the empty state
contains — bare terraces, empty plazas, quiet crater — never the things being removed.

Two strengths: 150 (a real edit) and 80 (looser, more room to erase). Look, then ONE pro roll
at 688x384 bridges the winner to full size.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wave5")
os.makedirs(OUT, exist_ok=True)

INIT = os.path.join(HERE, "wave1", "_init-688.png")  # cand1-ref at 400x224, made in wave1

DESCRIPTION = (
    "isometric pixel art volcanic island, an empty uninhabited stage: a quiet volcano with "
    "bare grass and dark rock slopes under a clear sky, wide empty stone terraces with low "
    "walls stepping down to the sea, broad bare staircases linking the terraces, a dark arched "
    "tunnel mouth in the upper terrace wall, an empty stone quay with a lighthouse on a "
    "breakwater arm, a sandy beach cove, every plaza and street bare flat flagstone, warm "
    "golden afternoon light from the upper left, clean hand-painted pixel art"
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
    run("H-init150", seed=5001, strength=150)
    run("I-init80", seed=5002, strength=80)
    print("wave5 complete: 2 generations spent", flush=True)
