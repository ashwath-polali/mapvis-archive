"""Waterfall spray: light-blue particles built from the painting's own water pixels.

Twenty generations failed at this, the same way they failed at smoke, and for the same
reason: PixelLab draws objects, not effects. So the particles are composed instead, out of
the exact four colours the hub painting uses for the panther-mouth falls, sampled straight
off the art:

    (252,254,254) white crest   (202,212,221) pale blue
    (170,199,175) mint          (126,159,173) deep blue-gray

Two sprites come out of this:
  spray-base  the impact at the bottom of a fall: droplets kicked up and out, mist rising
  spray-mouth a lighter drift for where the water leaves the panther's jaws

The loop is exact by construction: every particle's life is one full cycle, and the particles
are only phase-shifted copies, so frame N wraps onto frame 0 with nothing popping.
"""
import math
import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = 8

WHITE = (252, 254, 254)
PALE = (202, 212, 221)
MINT = (170, 199, 175)
DEEP = (126, 159, 173)


def px_put(img, x: int, y: int, col, a: float):
    """One pixel, alpha-composited by hand: no blending engine, no soft edges."""
    if a <= 0.02:
        return
    x, y = int(x), int(y)
    if x < 0 or y < 0 or x >= img.width or y >= img.height:
        return
    r, g, b = col
    old = img.getpixel((x, y))
    na = min(255, int(255 * a))
    if old[3] == 0:
        img.putpixel((x, y), (r, g, b, na))
    else:
        # keep the brighter of the two: droplets crossing mist should read as droplets
        if na > old[3]:
            img.putpixel((x, y), (r, g, b, na))


def blob(img, cx: float, cy: float, size: int, col, a: float):
    """A 1 to 3 px particle. Bigger ones get a paler core so they read as water, not dots."""
    if size <= 1:
        px_put(img, cx, cy, col, a)
        return
    if size == 2:
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            px_put(img, cx + dx, cy + dy, col, a)
        return
    for dx, dy in ((0, -1), (-1, 0), (0, 0), (1, 0), (0, 1)):
        px_put(img, cx + dx, cy + dy, col, a)
    px_put(img, cx, cy, WHITE, a)


def churn_row(img, t: float, W: int, H: int):
    """The churn where the water lands: short foam dashes sliding outward and fading.

    At map zoom a droplet is two screen pixels; what actually reads as motion is this
    band shifting, the same trick the engine's ocean foam uses.
    """
    cx = W / 2
    for lane, (y, speed, col) in enumerate(((H - 2, 1.0, WHITE), (H - 4, 0.7, PALE), (H - 6, 0.45, MINT))):
        for side in (-1, 1):
            for k in range(4):
                u = (t * speed + k * 0.25 + lane * 0.13) % 1.0
                x = cx + side * (2.5 + u * (W * 0.42))
                a = math.sin(math.pi * u) ** 0.8
                w = 2 if u < 0.55 else 1
                for dx in range(w):
                    px_put(img, x + side * dx, y, col, a * 0.95)


def build(name: str, W: int, H: int, particles: list, sheet_scale: int = 6, churn: bool = False):
    """particles: dicts of x0, spread, rise, size, col, arc, phase"""
    out_frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if churn:
            churn_row(img, t, W, H)
        for p in particles:
            u = (t + p["phase"]) % 1.0                    # this particle's own life, 0..1
            # rise with a little slow-down at the top, the way spray loses momentum
            y = H - 1 - p["rise"] * (1 - (1 - u) ** 1.6)
            # arc outward: sideways travel grows while the particle climbs
            x = p["x0"] + p["arc"] * u * p["spread"]
            # a lazy wobble so the column never reads as a straight line of dots
            x += math.sin(u * 6.283 + p["phase"] * 9.0) * 0.9
            # in fast, out slow, gone by the end of the life so the loop closes clean
            a = math.sin(math.pi * u) ** 0.7
            size = p["size"] if u < 0.6 else max(1, p["size"] - 1)
            blob(img, x, y, size, p["col"], a)
        img.save(os.path.join(OUT, f"{name}-{f}.png"))
        out_frames.append(img)

    sheet = Image.new("RGBA", (W * FRAMES + 4 * FRAMES, H), (18, 18, 22, 255))
    for i, fr in enumerate(out_frames):
        sheet.alpha_composite(fr, (i * (W + 4), 0))
    sheet.resize((sheet.width * sheet_scale, sheet.height * sheet_scale), Image.NEAREST).save(
        os.path.join(HERE, f"_{name}-sheet.png")
    )
    return out_frames


OUT = os.path.join(HERE, "spray")


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    # the impact: droplets thrown up and OUT, far enough to clear the white water and land
    # against dark rock, because 1px specks over a white fall are invisible at map zoom
    # (measured on the real painting, first pass). Fat droplets, wide arcs.
    base = []
    fan = [
        (-1.55, 14, 3, WHITE), (1.6, 13, 3, WHITE),
        (-1.15, 17, 2, PALE), (1.25, 16, 2, PALE),
        (-1.85, 10, 2, PALE), (1.9, 9, 2, PALE),
        (-0.85, 19, 2, WHITE), (0.9, 18, 2, WHITE),
        (-1.35, 12, 2, MINT), (1.4, 11, 2, MINT),
        (-2.1, 7, 2, DEEP), (2.15, 6, 2, DEEP),
    ]
    for i, (arc, rise, size, col) in enumerate(fan):
        base.append({
            "x0": 20, "spread": 7.0, "rise": rise, "size": size,
            "col": col, "arc": arc, "phase": (i * 0.618) % 1.0,   # golden stagger, never clumps
        })
    build("spray-base", 41, 26, base, churn=True)

    # the mouth: a thinner, gentler drift for where the water leaves the jaws
    mouth = []
    fan2 = [
        (-0.5, 9, 1, PALE), (0.55, 8, 1, PALE),
        (-0.25, 11, 1, WHITE), (0.3, 10, 1, WHITE),
        (0.0, 12, 2, PALE), (-0.7, 7, 1, MINT), (0.75, 7, 1, MINT),
    ]
    for i, (arc, rise, size, col) in enumerate(fan2):
        mouth.append({
            "x0": 8, "spread": 4.0, "rise": rise, "size": size,
            "col": col, "arc": arc, "phase": (i * 0.618) % 1.0,
        })
    build("spray-mouth", 17, 16, mouth)
    print("built spray-base and spray-mouth,", FRAMES, "frames each")


def install(scene_id: str = "hub", slow: int = 2):
    for name, w, h in (("spray-base", 41, 26), ("spray-mouth", 17, 16)):
        dst = os.path.join(r"C:\Users\ashcy\MAPVIS-next\work", scene_id, "library", name)
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(dst):
            os.remove(os.path.join(dst, f))
        k = 0
        for f in range(FRAMES):
            for _ in range(slow):
                shutil.copyfile(os.path.join(OUT, f"{name}-{f}.png"), os.path.join(dst, f"{k}.png"))
                k += 1
        print("installed", k, "frames into", dst)


if __name__ == "__main__":
    main()
    install()
