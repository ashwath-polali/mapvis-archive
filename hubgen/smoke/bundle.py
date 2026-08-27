"""A throwaway preview bundle: the hub painting with every built effect placed and moving.

MAPVIS is the real authoring path; this only exists so the effects can be judged IN MOTION,
in the engine, on the island they were made from, before Ash spends a click placing them. The
levels mask is a plain walkable band, enough for Thor to stand in frame.
"""
import json
import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = r"c:\Users\ashcy\AdventureGame\public\maps-painted"
BUNDLE = os.path.join(GAME, "hub-fx")
HUB = r"C:\Users\ashcy\MAPVIS-next\public\hub-final.png"

# measured off the painting: the two fall columns and where each lands
LEFT_FALL_X, RIGHT_FALL_X = 227, 464
FALL_TOP_Y, FALL_BASE_Y = 112, 170
CRATER = (340, 12)
# the cone's summit touches the canvas top, so a plume anchored on the crater rises
# straight off the map. One grow-top press in MAPVIS is the real fix; the preview
# simulates it, and everything below shifts by the same amount.
GROW_TOP = 104


def main():
    if os.path.isdir(BUNDLE):
        shutil.rmtree(BUNDLE)
    os.makedirs(os.path.join(BUNDLE, "assets"), exist_ok=True)

    hub = Image.open(HUB).convert("RGBA")
    W, H = hub.size
    hub.save(os.path.join(BUNDLE, "scene.png"))

    # a walkable band across the town terrace so Thor has ground under him
    lv = Image.new("L", (W, H), 0)
    for y in range(250, 300):
        for x in range(180, 520):
            if hub.getpixel((x, y))[3] > 40:
                lv.putpixel((x, y), 40)
    lv.convert("RGB").save(os.path.join(BUNDLE, "levels.png"))
    Image.new("RGB", (W, H), (0, 0, 0)).save(os.path.join(BUNDLE, "occluders.png"))

    assets = []

    def add_anim(src_dir: str, name: str, x: int, y: int, scale: float, fps: int, group: str):
        dst = os.path.join(BUNDLE, "assets", name)
        os.makedirs(dst, exist_ok=True)
        frames = sorted(
            (f for f in os.listdir(src_dir) if f.endswith(".png")),
            key=lambda f: int(os.path.splitext(f)[0]) if os.path.splitext(f)[0].isdigit() else 0,
        )
        rel = []
        for i, f in enumerate(frames):
            shutil.copyfile(os.path.join(src_dir, f), os.path.join(dst, f"{i}.png"))
            rel.append(f"assets/{name}/{i}.png")
        assets.append({
            "id": name, "group": group, "frames": rel, "fps": fps,
            "x": x, "y": y, "scale": scale, "scaleX": scale, "scaleY": scale,
            "rot": 0, "flipX": False, "flipY": False,
        })

    lib = r"C:\Users\ashcy\MAPVIS-next\work\hub\library"
    # the plume stands on the crater
    add_anim(os.path.join(lib, "smoke-plume"), "smoke-plume", CRATER[0], CRATER[1], 0.9, 7, "smoke")
    # the flow overlays sit ON each painted fall, top-anchored via a bottom-anchored sprite
    flow_h = Image.open(os.path.join(lib, "fall-flow", "0.png")).height
    for i, fx in enumerate((LEFT_FALL_X, RIGHT_FALL_X)):
        add_anim(os.path.join(lib, "fall-flow"), f"fall-flow-{i}", fx, FALL_TOP_Y + flow_h, 1.0, 10, "water")
        add_anim(os.path.join(lib, "spray-base"), f"spray-{i}", fx, FALL_BASE_Y + 4, 1.0, 8, "water")

    with open(os.path.join(BUNDLE, "assets.json"), "w", encoding="utf8") as fh:
        json.dump({"assets": assets}, fh, indent=2)

    with open(os.path.join(BUNDLE, "map.json"), "w", encoding="utf8") as fh:
        json.dump({
            "id": "hub-fx", "w": W, "h": H,
            "encoding": {"blocked": 0, "L0": 40, "ramp01": 50, "L1": 60, "ramp12": 70,
                         "L2": 80, "ramp23": 90, "L3": 100, "stepTolerance": 10},
            "spawn": [340, 275],
            "character": {"heightPx": 18, "hip": 2, "hipDY": 1},
            "speed": 34, "yScale": 0.72, "stairs": [], "occluders": [],
            "events": [],
        }, fh, indent=2)
    print("wrote", BUNDLE, "with", len(assets), "animated effects")


if __name__ == "__main__":
    main()
