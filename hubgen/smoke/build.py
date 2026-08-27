"""The volcano plume, built not generated: three bubbly puffs rising in a seamless loop.

Ash's spec (2026-08-16): "3 big clouds stacked on top of each other slightly animated in a
loop like they're moving, slight evaporating at the top", very slow, not fast ugly shit.
~20 generations produced nothing usable, so the pixels come from art that already exists:
wave16's plume, the best smoke any wave painted, in the island's own palette.

Craft notes. A puff is NOT a circle (v1 stacked perfect circles and read mechanical) but a
cluster of overlapping discs, so the silhouette is lumpy. Its fill is sampled from the real
plume, so the internal banding and dithering are PixelLab's, not a gradient. Light comes from
the upper left per ART.md: a lighter crown, a darker underside, a hue-shifted rim, never a
black outline.

The loop is exact: one shape, three slots, and over one cycle every puff advances exactly one
slot while a newborn takes the bottom, so the last frame lands on the first. Frames are
written twice for a slow playback at the library's default fps.
"""
import math
import os
import shutil

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PLUME = os.path.join(HERE, "plume-wave16.png")
OUT = os.path.join(HERE, "plume3")

W, H = 56, 96          # canvas: tall enough for three slots plus the fade-out
BASE = 30              # the puff's own drawn size before per-slot scaling
FRAMES = 8
CRATER = (342, 40)     # wave23's crater mouth, where the plume stands for the preview

# the three resting slots, bottom to top: y centre and size. A puff grows as it climbs,
# the way real smoke spreads, and the top one thins out. The lowest slot sits ON the
# canvas floor and the newborn starts below it, half-clipped: the sprite is placed with
# its feet at the crater, so smoke has to be leaving the bottom edge or the plume reads
# as floating above the mountain (it did, first pass).
SLOT_Y = [86, 66, 44, 20, -6]
SLOT_S = [0.45, 0.68, 0.90, 1.08, 1.20]
BORN_Y = 100
BORN_S = 0.25
PUFFS = len(SLOT_Y) - 1     # bodies on screen, plus the newborn climbing in


def puff_mask(size: int) -> Image.Image:
    """A lumpy cloud silhouette: overlapping discs, never one circle."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    c = size / 2
    # one body plus shoulders all the way round, radii and angles hand-picked so the
    # outline reads as bubbles rather than an arc, and never sits flat on its underside
    d.ellipse([c - size * 0.28, c - size * 0.24, c + size * 0.28, c + size * 0.24], fill=255)
    lobes = [
        (-0.24, -0.14, 0.21),
        (0.22, -0.18, 0.20),
        (0.00, -0.26, 0.23),
        (-0.28, 0.08, 0.18),
        (0.26, 0.06, 0.19),
        (-0.12, 0.20, 0.17),
        (0.14, 0.22, 0.16),
    ]
    for dx, dy, r in lobes:
        d.ellipse(
            [c + dx * size - r * size, c + dy * size - r * size,
             c + dx * size + r * size, c + dy * size + r * size],
            fill=255,
        )
    # a light blur then a hard threshold rounds the joins without softening the edge:
    # the silhouette stays one crisp pixel boundary, which is what keeps it pixel art
    m = m.filter(ImageFilter.GaussianBlur(size * 0.05))
    return m.point(lambda v: 255 if v > 128 else 0)


def sampled_fill(size: int) -> Image.Image:
    """Real plume pixels, lifted toward smoke.

    Straight from the painting the puffs read as brown rock: the plume's own pixels are
    dark and warm because they sit against a bright sky, while a puff drawn OVER the
    island has to separate from the cone behind it. So the sample is pulled most of the
    way to a pale warm gray, keeping PixelLab's banding as the texture underneath.
    """
    src = Image.open(PLUME).convert("RGBA")
    crop = src.crop((40, 4, 40 + 36, 4 + 36)).resize((size, size), Image.NEAREST)
    px = crop.load()
    for y in range(size):
        for x in range(size):
            r, g, b, a = px[x, y]
            lum = (r * 0.35 + g * 0.4 + b * 0.25)
            # toward a warm gray, and lifted well above the cone's value
            r = int(lum * 0.35 + 205 * 0.65)
            g = int(lum * 0.35 + 199 * 0.65)
            b = int(lum * 0.35 + 198 * 0.65)
            px[x, y] = (min(255, r), min(255, g), min(255, b), a)
    return crop


def build_puff(size: int) -> Image.Image:
    m = puff_mask(size)
    fill = sampled_fill(size)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(fill, (0, 0), m)
    px = out.load()
    mp = m.load()

    # light from the upper left: crown lifted, underside sunk, and a hue-shifted rim
    # (never black, per the style rules)
    for y in range(size):
        for x in range(size):
            if not mp[x, y]:
                continue
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            # how far into the blob this pixel sits, along the light axis
            k = ((x + y) / (2 * size)) - 0.5           # -0.5 upper-left .. +0.5 lower-right
            f = 1.0 - k * 0.34
            r = min(255, int(r * f))
            g = min(255, int(g * f))
            b = min(255, int(b * f))
            # the rim: any pixel whose lower-right neighbour is empty gets a cooler,
            # slightly deeper edge so the puff reads round without an outline pass
            edge = (x + 1 >= size or not mp[x + 1, y]) or (y + 1 >= size or not mp[x, y + 1])
            if edge:
                r, g, b = int(r * 0.86), int(g * 0.87), int(b * 0.92)
            px[x, y] = (r, g, b, a)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    puff = build_puff(BASE)
    frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # four bodies on screen at once: the newborn climbing into slot 0, and the three
        # that occupy slots 0..2, each sliding toward the slot above it
        for k in range(-1, PUFFS):
            y0 = SLOT_Y[k] if k >= 0 else BORN_Y
            s0 = SLOT_S[k] if k >= 0 else BORN_S
            y1, s1 = SLOT_Y[k + 1], SLOT_S[k + 1]
            y = y0 + (y1 - y0) * t
            s = s0 + (s1 - s0) * t
            size = max(3, round(BASE * s))
            p = puff.resize((size, size), Image.NEAREST)
            # alpha: the newborn fades in, the top one evaporates, the middle rides full
            a = 1.0
            if k == -1:
                a = min(1.0, t * 1.6)      # the newborn is solid as soon as it clears the rim
            elif k == PUFFS - 1:
                a = 1.0 - t * t            # the top holds, then lets go: evaporation, not a dimmer
            if a < 1.0:
                p.putalpha(p.getchannel("A").point(lambda v, a=a: int(v * a)))
            # a lazy sideways drift, the same on every cycle so the loop stays exact
            drift = math.sin((y / H) * 3.14159 * 2) * 2.0
            fr.alpha_composite(p, (round(W / 2 + drift - size / 2), round(y - size / 2)))
        fr.save(os.path.join(OUT, f"{f}.png"))
        frames.append(fr)

    # a contact sheet at 2x for the eye
    strip = Image.new("RGBA", (W * FRAMES + FRAMES * 2, H), (18, 18, 22, 255))
    for i, fr in enumerate(frames):
        strip.alpha_composite(fr, (i * (W + 2), 0))
    strip.resize((strip.width * 2, strip.height * 2), Image.NEAREST).save(
        os.path.join(HERE, "_strip-2x.png")
    )
    # and one still, big, to judge a single puff's craft
    frames[3].resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(HERE, "_still-4x.png"))

    # the only test that counts: the plume standing on the real crater, at the size the
    # game will draw it, on the painting it belongs to
    hub = Image.open(r"C:\Users\ashcy\MAPVIS-next\public\hub-final.png").convert("RGBA")
    for i, fr in enumerate(frames[::2]):
        stage = hub.copy()
        sc = 0.42                                   # plume height against the cone
        p = fr.resize((max(1, round(W * sc)), max(1, round(H * sc))), Image.NEAREST)
        stage.alpha_composite(p, (CRATER[0] - p.width // 2, CRATER[1] - p.height))
        crop = stage.crop((CRATER[0] - 150, 0, CRATER[0] + 150, 190))
        crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST).save(
            os.path.join(HERE, f"_oncrater-{i}.png")
        )
    print("built", FRAMES, "frames at", (W, H))


def install(scene_id: str = "hub", name: str = "smoke-plume", slow: int = 2):
    """Into a map's own library, each frame repeated so the loop plays slowly."""
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
    main()
    install()
