"""Conservative sea cut, second attempt after the heuristic cutter chipped candidate A.

Rules learned (2026-08-15): foam/pale rules eat stone highlights; per-palette color guessing
is not trustworthy. This version: seed colors are sampled ONLY from the slab's own outer edge
ring (opaque pixels touching the transparent margin), the flood accepts only pixels within a
tight distance of those seeds, and nothing else. The painted waterline foam against the island
STAYS (it reads as shoreline; the engine ocean laps underneath). Output is verified by eye at
4x before it is staged anywhere.

Also writes a QA sheet: the cut result 1x, plus magenta overlay of every removed pixel on the
original, plus 4x crops of the four coast quadrants.
"""
import os, sys
from collections import Counter, deque
from PIL import Image


def cut(src):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()

    # 1. find the transparent margin by flooding transparency from the borders
    outside = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if px[x, y][3] == 0:
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if px[x, y][3] == 0:
                q.append((x, y))
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or outside[y][x]:
            continue
        if px[x, y][3] != 0:
            continue
        outside[y][x] = True
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    # 2. seed palette: opaque pixels adjacent to the outside margin = the slab's outer ring
    ring = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] == 0:
                continue
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + ox, y + oy
                if 0 <= nx < w and 0 <= ny < h and outside[ny][nx]:
                    ring.append(px[x, y][:3])
                    break
    seeds = [c for c, _ in Counter(ring).most_common(12)]

    def near(c):
        r, g, b = c[:3]
        for sr, sg, sb in seeds:
            if abs(r - sr) + abs(g - sg) + abs(b - sb) <= 90:
                return True
        return False

    # 3. flood from the ring pixels themselves, only through seed-near colors
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for y in range(h):
        for x in range(w):
            if px[x, y][3] != 0 and not seen[y][x]:
                for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + ox, y + oy
                    if 0 <= nx < w and 0 <= ny < h and outside[ny][nx]:
                        q.append((x, y))
                        break
    cutset = []
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y][x]:
            continue
        seen[y][x] = True
        if px[x, y][3] == 0 or not near(px[x, y]):
            continue
        cutset.append((x, y))
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    out = im.copy()
    opx = out.load()
    for x, y in cutset:
        opx[x, y] = (0, 0, 0, 0)
    base = os.path.splitext(src)[0]
    outp = base + "-noocean2.png"
    out.save(outp)

    # 4. QA: magenta overlay of removed pixels on the original
    qa = im.copy().convert("RGBA")
    qpx = qa.load()
    for x, y in cutset:
        qpx[x, y] = (255, 0, 200, 255)
    qa.save(base + "-cutQA.png")

    # 5. 4x crops of the coast quadrants of the RESULT
    qdir = os.path.join(os.path.dirname(base), "qa4x")
    os.makedirs(qdir, exist_ok=True)
    quads = {"nw": (0, 0, w // 2, h // 2), "ne": (w // 2, 0, w, h // 2),
             "sw": (0, h // 2, w // 2, h), "se": (w // 2, h // 2, w, h)}
    for name, box in quads.items():
        c = out.crop(box)
        c = c.resize((c.width * 4, c.height * 4), Image.NEAREST)
        c.save(os.path.join(qdir, f"{os.path.basename(base)}-{name}-4x.png"))

    print(f"cut {len(cutset)} px, {len(seeds)} seed colors -> {outp}")
    return outp


if __name__ == "__main__":
    cut(sys.argv[1])
