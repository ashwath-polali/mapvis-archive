"""
pixeltex.py - tileable pixel-art architecture textures, procedural, zero cost.

Why this exists: Octopath's buildings are boxes with prism roofs. Every cornice,
sill, window surround, brick and shingle you see is PAINTED, not modelled (verified
at native pixels against reference/octopath-bar/). So the texture set is where the
detail lives, and it has to be authorable by machine or the tool does not scale.

Every texture is:
  - seamlessly tileable (all noise is generated on a torus)
  - quantised to a fixed palette (no gradients, no antialiasing)
  - authored at a stated texel size in metres, so texel density is a build constant

No model looks at anything. Inputs are dimensions and a palette.

    py pixeltex.py --out tex/
"""
import argparse
import os

import numpy as np

# Mechanically extracted by k-means over 50 Octopath town frames (see PALETTE.md).
PAL = np.array([
    [5, 6, 5], [26, 14, 9], [14, 21, 29], [42, 32, 23],
    [67, 46, 27], [35, 47, 63], [80, 69, 52], [115, 69, 32],
    [51, 79, 108], [113, 99, 76], [163, 109, 56], [87, 121, 156],
    [158, 137, 104], [143, 168, 189], [198, 174, 134], [220, 216, 206],
], dtype=np.float32)


def _rng(seed):
    return np.random.default_rng(seed)


def tile_noise(n, freq, seed, octaves=4):
    """Value noise on a torus, so it tiles by construction."""
    rng = _rng(seed)
    out = np.zeros((n, n), np.float32)
    amp, f = 1.0, freq
    for _ in range(octaves):
        g = rng.random((f, f)).astype(np.float32)
        # bilinear upsample with wraparound
        idx = np.arange(n) * f / n
        i0 = np.floor(idx).astype(int) % f
        i1 = (i0 + 1) % f
        t = (idx - np.floor(idx)).astype(np.float32)
        a = g[i0][:, i0] * (1 - t)[:, None] + g[i1][:, i0] * t[:, None]
        b = g[i0][:, i1] * (1 - t)[:, None] + g[i1][:, i1] * t[:, None]
        out += amp * (a * (1 - t)[None, :] + b * t[None, :])
        amp *= 0.5
        f *= 2
    out -= out.min()
    return out / (out.max() + 1e-9)


def quantise(rgb, ramp):
    """Snap every pixel to the nearest colour in `ramp`. This is what makes it read
    as pixel art rather than as a render: hard steps, no gradient."""
    flat = rgb.reshape(-1, 3)
    d = ((flat[:, None, :] - ramp[None, :, :]) ** 2).sum(2)
    return ramp[d.argmin(1)].reshape(rgb.shape).astype(np.uint8)


def ramp_from(indices, lighten=0.0):
    r = PAL[list(indices)].copy()
    return np.clip(r + lighten, 0, 255)


def _shade(mask_edges, base, hi, lo):
    """Give a masonry unit a lit top-left arris and a dark bottom-right one.
    This is the single trick that makes flat paint read as relief."""
    out = np.repeat(base[..., None], 3, axis=2)
    return out, hi, lo


# ---------------------------------------------------------------- generators

def masonry(n, seed, rows, cols, ramp, stagger=True, mortar=0.10, jitter=0.25):
    """Coursed stone / brick. Staggered vertical joints - continuous ones read as a
    radiator, which is the defect logged in MAPVIS/docs/HOW-IT-WORKS.md."""
    rng = _rng(seed)
    img = np.zeros((n, n, 3), np.float32)
    rh = n / rows
    grain = tile_noise(n, 8, seed + 1)
    for r in range(rows):
        y0, y1 = int(r * rh), int((r + 1) * rh)
        off = (0.5 if (stagger and r % 2) else 0.0)
        cw = n / cols
        for c in range(-1, cols + 1):
            x0 = int((c + off) * cw)
            x1 = int((c + 1 + off) * cw)
            if x1 <= 0 or x0 >= n:
                continue
            xa, xb = max(0, x0), min(n, x1)
            tone = 0.55 + jitter * rng.random()
            blk = np.zeros((y1 - y0, xb - xa, 3), np.float32)
            blk[:] = tone
            m = max(1, int(rh * mortar))
            blk[:m] *= 1.28          # lit top arris
            blk[-m:] *= 0.62         # shadowed bottom arris
            blk[:, :m] *= 1.16
            blk[:, -m:] *= 0.70
            img[y0:y1, xa:xb] = blk
    img *= (0.85 + 0.30 * grain)[..., None]
    rgb = np.clip(img, 0, 1) * 255
    lo, hi = ramp[0], ramp[-1]
    tinted = lo[None, None, :] + (hi - lo)[None, None, :] * (rgb / 255.0)
    return quantise(tinted, ramp)


def cobble(n, seed, cells, ramp):
    """Ground. Irregular cells, not a grid - a grid reads as tile and kills it."""
    rng = _rng(seed)
    pts = rng.random((cells, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    best = np.full((n, n), 1e9, np.float32)
    who = np.zeros((n, n), np.int32)
    for i, (py, px) in enumerate(pts):                    # toroidal Voronoi
        dy = np.abs(yy - py); dy = np.minimum(dy, n - dy)
        dx = np.abs(xx - px); dx = np.minimum(dx, n - dx)
        d = dy * dy + dx * dx
        m = d < best
        best[m] = d[m]; who[m] = i
    tone = rng.random(cells).astype(np.float32)[who] * 0.34 + 0.56
    edge = np.zeros((n, n), bool)
    for ax in (0, 1):
        edge |= who != np.roll(who, 1, axis=ax)
        edge |= who != np.roll(who, -1, axis=ax)
    tone[edge] *= 0.55
    tone *= 0.86 + 0.28 * tile_noise(n, 6, seed + 3)
    rgb = np.repeat(np.clip(tone, 0, 1)[..., None], 3, axis=2) * 255
    lo, hi = ramp[0], ramp[-1]
    return quantise(lo + (hi - lo) * (rgb / 255.0), ramp)


def shingle(n, seed, rows, cols, ramp):
    """Roof. Overlapping scallops with a hard shadow line under each course."""
    rng = _rng(seed)
    img = np.zeros((n, n), np.float32)
    rh = n / rows
    cw = n / cols
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    for r in range(rows):
        for c in range(-1, cols + 1):
            off = (0.5 if r % 2 else 0.0)
            cy = (r + 0.5) * rh
            cx = (c + off + 0.5) * cw
            dy = (yy - cy) / (rh * 0.95)
            dx = np.abs(xx - cx); dx = np.minimum(dx, n - dx) / (cw * 0.62)
            m = (dx ** 2 + np.clip(dy, -1, 1) ** 2) < 1.0
            img[m] = 0.52 + 0.34 * rng.random()
            img[m & (dy > 0.45)] *= 0.55           # shadow under the lap
            img[m & (dy < -0.55)] *= 1.30          # lit nose
    img[img == 0] = 0.30
    img *= 0.88 + 0.24 * tile_noise(n, 8, seed + 5)
    rgb = np.repeat(np.clip(img, 0, 1)[..., None], 3, axis=2) * 255
    lo, hi = ramp[0], ramp[-1]
    return quantise(lo + (hi - lo) * (rgb / 255.0), ramp)


def plaster_timber(n, seed, ramp_p, ramp_t, beam=0.11):
    """Half-timbering. The frame is PAINTED - Octopath does not model it."""
    rng = _rng(seed)
    base = 0.66 + 0.26 * tile_noise(n, 5, seed)
    rgb = np.repeat(base[..., None], 3, axis=2) * 255
    lo, hi = ramp_p[0], ramp_p[-1]
    out = quantise(lo + (hi - lo) * (rgb / 255.0), ramp_p).astype(np.float32)
    b = max(2, int(n * beam))
    tim = ramp_t[-2]
    dark = ramp_t[0]
    def bar(sl_y, sl_x):
        out[sl_y, sl_x] = tim
        # one-pixel shadow on the underside sells the paint as relief
        ys = slice(min(n - 1, sl_y.stop), min(n, sl_y.stop + max(1, b // 3))) if sl_y.stop else sl_y
        if sl_y.stop and sl_y.stop + 1 < n:
            out[sl_y.stop:sl_y.stop + max(1, b // 3), sl_x] = dark
    bar(slice(0, b), slice(0, n))
    bar(slice(n - b, n), slice(0, n))
    # posts only. A diagonal brace does not tile - it reads as a repeating X across
    # the wall, which is worse than no brace at all.
    for x in (0, n // 2 - b // 2, n - b):
        out[:, x:x + b] = tim
        if x + b < n:
            out[:, x + b:x + b + max(1, b // 3)] = dark
    mid = n // 2 - b // 2                                  # one mid rail
    out[mid:mid + b, :] = tim
    out[mid + b:mid + b + max(1, b // 3), :] = dark
    return out.astype(np.uint8)


def plank(n, seed, count, ramp, vertical=True):
    rng = _rng(seed)
    img = np.zeros((n, n), np.float32)
    w = n / count
    for i in range(count):
        a, b = int(i * w), int((i + 1) * w)
        t = 0.52 + 0.34 * rng.random()
        img[:, a:b] = t
        img[:, a:a + 1] = t * 1.25
        img[:, max(a, b - 1):b] = t * 0.55
    img *= 0.86 + 0.26 * tile_noise(n, 16, seed + 9)     # long grain
    if not vertical:
        img = img.T
    rgb = np.repeat(np.clip(img, 0, 1)[..., None], 3, axis=2) * 255
    lo, hi = ramp[0], ramp[-1]
    return quantise(lo + (hi - lo) * (rgb / 255.0), ramp)


def dirt(n, seed, ramp):
    g = 0.5 * tile_noise(n, 4, seed) + 0.35 * tile_noise(n, 12, seed + 1) + 0.15 * tile_noise(n, 32, seed + 2)
    g = (g - g.min()) / (g.max() - g.min())
    rgb = np.repeat((0.48 + 0.44 * g)[..., None], 3, axis=2) * 255
    lo, hi = ramp[0], ramp[-1]
    return quantise(lo + (hi - lo) * (rgb / 255.0), ramp)


# ---------------------------------------------------------------- the set

def build(out_dir, n=64):
    """The smallest material set that covers an Octopath town block. Eight.
    Texel size is stated per material; the scene builder scales UVs to match."""
    os.makedirs(out_dir, exist_ok=True)
    warm_stone = ramp_from([3, 6, 9, 12, 14, 15])
    grey_stone = ramp_from([1, 3, 6, 9, 12, 14])
    brick_r    = ramp_from([1, 4, 7, 10, 14])
    roof_r     = ramp_from([0, 1, 3, 4, 7, 10])
    plaster_r  = ramp_from([6, 9, 12, 14, 15])
    timber_r   = ramp_from([0, 1, 3, 4, 7])
    ground_r   = ramp_from([3, 6, 9, 12, 14])
    earth_r    = ramp_from([1, 3, 6, 9, 12])

    tex = {
        # name            image                                               texel size (m/tile)
        'cobble':        (cobble(n, 11, 72, ground_r),                        2.0),
        'dirt':          (dirt(n, 12, earth_r),                               3.0),
        'stone_course':  (masonry(n, 13, 9, 5, warm_stone),                   2.0),
        'quay_block':    (masonry(n, 14, 8, 5, grey_stone, jitter=0.18),      2.4),
        'brick':         (masonry(n, 15, 10, 5, brick_r, mortar=0.14),        1.6),
        'shingle':       (shingle(n, 16, 8, 8, roof_r),                       1.6),
        'plaster_timber':(plaster_timber(n, 17, plaster_r, timber_r),         3.0),
        'plank':         (plank(n, 18, 7, timber_r),                          1.4),
    }
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit('Pillow required')
    lines = []
    for name, (img, texel) in tex.items():
        p = os.path.join(out_dir, name + '.png')
        Image.fromarray(img).save(p)
        lines.append(f'{name:16s} {n}x{n}px  {texel:.1f} m/tile  -> {n / texel:.0f} texel/m')
        print(lines[-1])
    with open(os.path.join(out_dir, 'MANIFEST.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return tex


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='tex')
    ap.add_argument('--size', type=int, default=64)
    a = ap.parse_args()
    build(a.out, a.size)
