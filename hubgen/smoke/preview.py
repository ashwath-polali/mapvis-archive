"""The plume judged where it will live: on the crater, over the engine's sea, at game scale.

The hub painting's cone reaches the canvas top (summit at y=2), so a plume has nowhere to
rise. MAPVIS's grow-top does exactly this for real; here it is simulated so the sprite can be
judged before Ash spends a click. In pmap there is no sky: everything outside the painting is
the animated ocean, so the smoke drifts over water, which is what an island looks like from
this angle anyway.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HUB = r"C:\Users\ashcy\MAPVIS-next\public\hub-final.png"
FRAMES = os.path.join(HERE, "plume3")
CRATER = (340, 10)      # the crater mouth in the painting's own pixels
GROW = 96               # how much sky the map would gain from one grow-top press
SEA = (32, 92, 104, 255)


def sheet(scale: float, name: str):
    hub = Image.open(HUB).convert("RGBA")
    W, H = hub.size
    stage_w, stage_h = W, H + GROW
    shots = []
    for i in (0, 2, 4, 6):
        fr = Image.open(os.path.join(FRAMES, f"{i}.png")).convert("RGBA")
        p = fr.resize((max(1, round(fr.width * scale)), max(1, round(fr.height * scale))), Image.NEAREST)
        stage = Image.new("RGBA", (stage_w, stage_h), SEA)
        stage.alpha_composite(hub, (0, GROW))
        # feet anchor, the same convention the game places assets by
        stage.alpha_composite(p, (CRATER[0] - p.width // 2, GROW + CRATER[1] - p.height))
        crop = stage.crop((CRATER[0] - 130, 0, CRATER[0] + 130, 230))
        shots.append(crop)
    sheet = Image.new("RGBA", (shots[0].width * len(shots) + 8 * len(shots), shots[0].height), (18, 18, 22, 255))
    for i, s in enumerate(shots):
        sheet.alpha_composite(s, (i * (s.width + 8), 0))
    sheet = sheet.resize((round(sheet.width * 1.6), round(sheet.height * 1.6)), Image.NEAREST)
    sheet.save(os.path.join(HERE, name))
    print("wrote", name, "at scale", scale)


if __name__ == "__main__":
    sheet(0.85, "_game-0.85.png")
    sheet(1.25, "_game-1.25.png")
