"""Zero-generation utilities for the hub candidates.

cut_ocean(src)      -> writes <src>-noocean.png. Deterministic: flood-fills from the image
                       borders through sea-colored pixels (blue-dominant slab + neutral foam)
                       and sets them transparent. Land pixels are never touched; nothing is
                       invented. The engine ocean replaces what was cut.
upscale_compare(src)-> writes side-by-side crops: nearest 2x (the true 1:1) vs EPX/Scale2x 2x
                       (deterministic neighborhood rule, smooths stair-steps, no hallucination)
                       so a human eye can pick. Also a 4x nearest detail crop.
"""
import os, sys
from collections import deque
from PIL import Image


def _is_sea(r, g, b, a):
    if a == 0:
        return True  # already transparent: the flood passes through
    foam = r > 195 and g > 195 and b > 195 and abs(r - g) < 25 and abs(g - b) < 25
    blue = b > r + 20 and b >= g - 25
    # the slab's dark navy border line: dark AND blue-leaning (volcanic brown rock has r > b
    # and stays; the tunnel mouth is interior, the flood can never reach it)
    navy = max(r, g, b) < 80 and b >= r and b >= g
    # wave4-style milky water: near-neutral pale sheen, and light teal shallows. Warm surfaces
    # (sand, flagstone, roofs) are r-dominant and never match either.
    milk = min(r, g, b) > 150 and max(r, g, b) - min(r, g, b) < 25
    teal = g > r + 8 and b > r + 8 and min(r, g, b) > 130
    return foam or blue or navy or milk or teal


def cut_ocean(src):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y))
    cut = 0
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y][x]:
            continue
        seen[y][x] = True
        r, g, b, a = px[x, y]
        if not _is_sea(r, g, b, a):
            continue
        if a != 0:
            px[x, y] = (0, 0, 0, 0)
            cut += 1
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    out = os.path.splitext(src)[0] + "-noocean.png"
    im.save(out)
    print(f"cut {cut} sea pixels -> {out}")
    return out


def _epx2x(im):
    im = im.convert("RGBA")
    w, h = im.size
    src = im.load()
    out = Image.new("RGBA", (w * 2, h * 2))
    dst = out.load()

    def at(x, y):
        return src[min(max(x, 0), w - 1), min(max(y, 0), h - 1)]

    for y in range(h):
        for x in range(w):
            p = at(x, y)
            a_, b_, c_, d_ = at(x, y - 1), at(x + 1, y), at(x - 1, y), at(x, y + 1)
            e0 = c_ if c_ == a_ and c_ != d_ and a_ != b_ else p
            e1 = b_ if a_ == b_ and a_ != c_ and b_ != d_ else p
            e2 = d_ if d_ == c_ and d_ != b_ and c_ != a_ else p
            e3 = b_ if b_ == d_ and b_ != a_ and d_ != c_ else p
            dst[2 * x, 2 * y] = e0
            dst[2 * x + 1, 2 * y] = e1
            dst[2 * x, 2 * y + 1] = e2
            dst[2 * x + 1, 2 * y + 1] = e3
    return out


def upscale_compare(src, crop=None):
    here = os.path.dirname(os.path.abspath(src))
    outdir = os.path.join(os.path.dirname(here), "compare")
    os.makedirs(outdir, exist_ok=True)
    im = Image.open(src).convert("RGBA")
    if crop:
        im = im.crop(crop)
    near2 = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    epx2 = _epx2x(im)
    side = Image.new("RGBA", (near2.width * 2 + 8, near2.height), (30, 30, 34, 255))
    side.paste(near2, (0, 0))
    side.paste(epx2, (near2.width + 8, 0))
    p1 = os.path.join(outdir, "nearest2x-vs-epx2x.png")
    side.save(p1)
    near4 = im.resize((im.width * 4, im.height * 4), Image.NEAREST)
    p2 = os.path.join(outdir, "detail-nearest-4x.png")
    near4.save(p2)
    print("wrote", p1)
    print("wrote", p2)


if __name__ == "__main__":
    src = sys.argv[1]
    cut_ocean(src)
    # town-center crop for the scaling comparison (left, top, right, bottom)
    upscale_compare(src, crop=(220, 120, 560, 320))
