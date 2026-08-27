"""The falls come alive: a scrolling streak overlay that sits ON the painted waterfall.

Particles around a fall are nearly invisible at map zoom (measured: 1-2 px specks against
pale water read as nothing). What reads is the water MOVING, so this is an overlay sprite,
not a decoration: narrow vertical streaks in the painting's own four water colours, scrolling
downward on a seamless loop, placed over the painted fall so the paint appears to flow.

The scroll loops exactly because the streak pattern is periodic in y with period PERIOD, and
each frame shifts it by PERIOD / FRAMES. The sides fade out so the overlay melts into the
painted column instead of showing a hard rectangle.
"""
import math
import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "flow")
FRAMES = 8
PERIOD = 16          # px of vertical pattern, so the loop closes on an integer shift

WHITE = (252, 254, 254)
PALE = (202, 212, 221)
MINT = (170, 199, 175)
DEEP = (126, 159, 173)

W, H = 13, 58        # the left fall measures about 11 px across and 57 tall

# per column: colour, dash length, gap, phase, and how strongly it shows
COLUMNS = [
    (DEEP, 3, 5, 0.10, 0.55),
    (PALE, 5, 3, 0.62, 0.85),
    (WHITE, 7, 3, 0.25, 1.00),
    (WHITE, 4, 6, 0.80, 0.90),
    (PALE, 6, 4, 0.40, 0.85),
    (MINT, 3, 7, 0.05, 0.60),
    (PALE, 5, 4, 0.70, 0.80),
    (WHITE, 6, 4, 0.15, 0.95),
    (PALE, 4, 5, 0.50, 0.80),
    (DEEP, 3, 6, 0.90, 0.55),
    (MINT, 4, 6, 0.35, 0.55),
    (PALE, 3, 7, 0.55, 0.50),
    (DEEP, 2, 8, 0.20, 0.40),
]


def build():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    frames = []
    for f in range(FRAMES):
        shift = (f * PERIOD) / FRAMES
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for x, (col, dash, gap, phase, strength) in enumerate(COLUMNS[:W]):
            span = dash + gap
            # the column's own edge falloff: the overlay has to melt into the paint
            edge = 1.0 - abs((x + 0.5) / W - 0.5) * 2.0        # 1 at the centre, 0 at the sides
            edge = min(1.0, edge * 1.8)
            for y in range(H):
                u = ((y + shift + phase * PERIOD) % span)
                if u >= dash:
                    continue
                # a streak is brightest in its middle and tapers at both ends
                k = math.sin(math.pi * (u / dash)) ** 0.6
                # the fall thins and brightens as it drops, then breaks up at the very end
                depth = 1.0 - 0.35 * (y / H)
                if y > H - 8:
                    depth *= max(0.0, (H - y) / 8.0)
                a = strength * k * edge * depth * 0.9
                if a <= 0.03:
                    continue
                img.putpixel((x, y), (col[0], col[1], col[2], min(255, int(255 * a))))
        img.save(os.path.join(OUT, f"{f}.png"))
        frames.append(img)

    sheet = Image.new("RGBA", (W * FRAMES + 4 * FRAMES, H), (18, 18, 22, 255))
    for i, fr in enumerate(frames):
        sheet.alpha_composite(fr, (i * (W + 4), 0))
    sheet.resize((sheet.width * 5, sheet.height * 5), Image.NEAREST).save(
        os.path.join(HERE, "_flow-sheet.png")
    )
    print("built", FRAMES, "flow frames at", (W, H))


def install(scene_id: str = "hub", name: str = "fall-flow", slow: int = 1):
    dst = os.path.join(r"C:\Users\ashcy\MAPVIS-next\work", scene_id, "library", name)
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(dst):
        os.remove(os.path.join(dst, f))
    k = 0
    for f in range(FRAMES):
        for _ in range(slow):
            shutil.copyfile(os.path.join(OUT, f"{f}.png"), os.path.join(dst, f"{k}.png"))
            k += 1
    print("installed", k, "frames into", dst)


if __name__ == "__main__":
    build()
    install()
