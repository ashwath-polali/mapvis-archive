"""Hub-island wave 1: three pixflux generations, three approaches, 3 generations total.

The brief (Ash, 2026-08-14): a cand1-TYPE island — volcano, terraced stone harbor town,
staircases, tunnel mouth, lighthouse, beach — but EMPTIER and CLEANER than cand-1, so a human
can trace walkability fast in MAPVIS and life-capable things (trees, people, shops) can be
added later as separate animated assets. Transparent background: the engine owns the ocean.

Approaches:
  A  type-text        pure text, the full cand1-type description, empty-clean phrased positively
  B  structure-text   pure text, emphasis on flat open terraces and readable walkable ground
  C  init-composition cand1-ref-512 resized as init at strength 60 (composition only)

Size note (measured 2026-08-14): /v1/generate-image-pixflux caps at 400px per side, so drafts
run at 400x224 (the 16:9 max) WITH ocean (v1 has no transparency). Full 688x384 with transparent
coast is the pro endpoint only (20-40 gens/call) and is wave 2, spent only on a direction that
survived the drafts.

Stop rule: a human (or the session) LOOKS at all three before any further spend.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wave1")
os.makedirs(OUT, exist_ok=True)

STYLE = "warm golden afternoon light from the upper left, clean hand-painted pixel art"

PROMPT_A = (
    "isometric pixel art volcanic island port town: a smoking volcano at the back with lush "
    "palm jungle slopes, a terraced stone citadel town stepping down to a wide harbor quay, "
    "broad empty flagstone plazas and wide stone staircases, a dark arched tunnel mouth in the "
    "citadel wall, a stone lighthouse on a breakwater arm, a sandy beach cove on the west side, "
    "bare open streets and empty squares with clear walkable ground, " + STYLE
)

PROMPT_B = (
    "isometric pixel art island seen from above, one volcanic island filling the frame: smoking "
    "volcano crater at the north, a ring of palm jungle below it, a walled stone harbor town "
    "built on three flat terraces stepping down to the sea, each terrace a wide open flagstone "
    "platform, broad stone staircases linking the terraces, an arched stone tunnel entrance set "
    "into the upper wall, a long stone quay with a lighthouse breakwater, a small sandy beach, "
    "open uncluttered ground everywhere, " + STYLE
)

PROMPT_C = (
    "isometric pixel art volcanic island port town, emptier and cleaner: open flagstone plazas, "
    "a bare stone quay, wide staircases between flat terraces, a dark arched tunnel mouth in the "
    "citadel wall, a stone lighthouse on a breakwater, a sandy beach cove, clear walkable "
    "streets and squares, " + STYLE
)

INIT = os.path.join(OUT, "_init-688.png")


def make_init():
    from PIL import Image
    src = r"C:\Users\ashcy\AdventureGame\reference\painted-scenes\island\cand1-ref-512.png"
    im = Image.open(src).convert("RGBA").resize((400, 224), Image.LANCZOS)
    im.save(INIT)


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
    make_init()
    run("A-type-text", PROMPT_A, seed=1001)
    run("B-structure-text", PROMPT_B, seed=1002)
    run("C-init-composition", PROMPT_C, seed=1003, init=INIT)
    print("wave1 complete: 3 generations spent", flush=True)
