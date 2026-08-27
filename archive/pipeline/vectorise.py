"""
vectorise.py - raster level field -> clean architectural polylines.

Why this file exists: the single worst defect in this project's history is
"melted geometry" - terrain built as per-cell block columns, so every terrace
edge is a staircase of 1 m crumbs. Octopath's ground is continuous flat planes
with single clean lofted faces at the level changes.

So the level field is traced with marching squares into closed loops, then
simplified with Douglas-Peucker, and the BUILDER only ever sees polygons. There
is no per-cell geometry anywhere downstream.

Also derived here, all as forced consequences of the level field:
  - retaining runs  (a level boundary on land)
  - parapet runs    (a walkable edge with a fall beside it)   ED-2
  - stair sites     (a street crossing a level boundary)      EL-5
  - quay runs       (land meeting sea)
"""
import json
import math
import os

import numpy as np

# marching-squares segment table, cell corners (bl, br, tr, tl) -> edge pairs.
# edges: 0 bottom, 1 right, 2 top, 3 left
_MS = {
    1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)],
    5: [(3, 2), (0, 1)], 6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)],
    9: [(2, 0)], 10: [(2, 3), (0, 1)], 11: [(2, 1)], 12: [(1, 3)],
    13: [(1, 0)], 14: [(0, 3)],
}
_EDGE_MID = {0: (0.5, 0.0), 1: (1.0, 0.5), 2: (0.5, 1.0), 3: (0.0, 0.5)}


def marching_squares(mask):
    """Closed loops around a binary mask, on the cell grid. Deterministic."""
    m = np.pad(mask.astype(np.uint8), 1)
    H, W = m.shape
    segs = []
    for y in range(H - 1):
        for x in range(W - 1):
            code = (m[y, x] | (m[y, x + 1] << 1) | (m[y + 1, x + 1] << 2)
                    | (m[y + 1, x] << 3))
            if code in (0, 15):
                continue
            for a, b in _MS[code]:
                ax, ay = _EDGE_MID[a]
                bx, by = _EDGE_MID[b]
                segs.append(((x + ax - 1, y + ay - 1), (x + bx - 1, y + by - 1)))
    return chain(segs)


def chain(segs, tol=1e-6):
    """Join segments end-to-end into polylines / closed loops."""
    def key(p):
        return (round(p[0], 4), round(p[1], 4))

    adj = {}
    for a, b in segs:
        adj.setdefault(key(a), []).append((key(b), b))
        adj.setdefault(key(b), []).append((key(a), a))
    used = set()
    loops = []
    for a, b in segs:
        ka, kb = key(a), key(b)
        if (ka, kb) in used or (kb, ka) in used:
            continue
        poly = [a, b]
        used.add((ka, kb))
        cur, prev = kb, ka
        while True:
            nxt = None
            for k2, p2 in adj.get(cur, []):
                if k2 == prev:
                    continue
                if (cur, k2) in used or (k2, cur) in used:
                    continue
                nxt = (k2, p2)
                break
            if nxt is None:
                break
            used.add((cur, nxt[0]))
            poly.append(nxt[1])
            prev, cur = cur, nxt[0]
            if cur == key(poly[0]):
                break
        if len(poly) >= 4:
            loops.append(poly)
    return loops


def rdp(pts, eps):
    """Douglas-Peucker. This is what turns a 1 m staircase into a straight run."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    best, bi = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = (abs(dy * px - dx * py + bx * ay - by * ax) / n if n > 1e-9
             else math.hypot(px - ax, py - ay))
        if d > best:
            best, bi = d, i
    if best <= eps:
        return [pts[0], pts[-1]]
    return rdp(pts[:bi + 1], eps)[:-1] + rdp(pts[bi:], eps)


def signed_area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return s / 2


# The corner-canting operation moved to ops_edges.py, where it belongs with the
# rest of the plan/profile vocabulary and where it grew the fixes this version
# needed (coincident-point guard, z interpolation, spike collapse, pier-stop
# reporting). Kept under the old name so every call site here is unchanged.
from ops_edges import chamfer_corners as chamfer          # noqa: E402


def clean_loops(mask, res, eps_m=2.2, min_area_m2=45.0):
    """Traced, simplified, area-filtered, consistently wound loops in metres."""
    out = []
    for loop in marching_squares(mask):
        closed = math.dist(loop[0], loop[-1]) < 1e-6
        pts = loop[:-1] if closed else loop
        if len(pts) < 4:
            continue
        pts = [(p[0] * res, p[1] * res) for p in pts]
        s = rdp(pts + [pts[0]], eps_m)[:-1]
        if len(s) < 3:
            continue
        a = signed_area(s)
        if abs(a) < min_area_m2:
            continue
        if a < 0:
            s = s[::-1]
        s = chamfer(s, closed=True)
        out.append([[round(x, 2), round(y, 2)] for x, y in s])
    return out


def runs_from_mask(mask, res, eps_m=2.0, min_len_m=4.0):
    """Open polylines for wall/parapet/quay runs, not closed regions."""
    out = []
    for loop in marching_squares(mask):
        pts = [(p[0] * res, p[1] * res) for p in loop]
        s = rdp(pts, eps_m)
        L = sum(math.dist(s[i], s[i + 1]) for i in range(len(s) - 1))
        if L >= min_len_m and len(s) >= 2:
            s = chamfer(s, closed=False)
            out.append([[round(x, 2), round(y, 2)] for x, y in s])
    return out


def stair_sites(lvl, street, walk, res, step_m, min_gap_m=22.0):
    """EL-5: two adjacent levels are impassable unless a connector joins them.
    A stair is FORCED wherever the street network crosses a level boundary.

    A stair is sized like a stair, NOT like the blob of street cells around the
    crossing. The earlier version flooded the neighbourhood and emitted the
    bounding box of the flood, which produced 40 "stairs" covering 18,053 m2
    against 11,349 m2 of walkable ground - the whole map was stairs. Its width
    is now the street's own width at the crossing, and its run is set by real
    stair geometry (riser/going), not by how far the flood ran."""
    H, W = lvl.shape
    RISER = 0.175                                  # metres, EL-3 band
    GOING = 0.30
    cand = []
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            if not street[y, x] or lvl[y, x] < 0:
                continue
            a = int(lvl[y, x])
            for dy, dx in ((1, 0), (0, 1)):
                b = int(lvl[y + dy, x + dx])
                if b < 0 or b == a or not street[y + dy, x + dx]:
                    continue
                cand.append((y, x, min(a, b), max(a, b)))
                break

    # one stair per crossing: greedily keep candidates that are far apart
    kept = []
    for y, x, lo, hi in cand:
        if all((y - ky) ** 2 + (x - kx) ** 2 > (min_gap_m / res) ** 2
               for ky, kx, _, _ in kept):
            kept.append((y, x, lo, hi))

    sites = []
    for y, x, lo, hi in kept:
        rise = (hi - lo) * step_m
        # ascent direction = local gradient of the level field
        gy = float(lvl[min(H - 1, y + 2), x]) - float(lvl[max(0, y - 2), x])
        gx = float(lvl[y, min(W - 1, x + 2)]) - float(lvl[y, max(0, x - 2)])
        m = math.hypot(gx, gy)
        if m < 1e-6:
            continue
        ux, uy = gx / m, gy / m                    # unit vector, uphill
        # street width measured ACROSS the ascent direction
        px, py = -uy, ux
        wcells = 0
        for t in range(1, 14):
            ok = False
            for s in (1, -1):
                sy = int(round(y + py * t * s))
                sx = int(round(x + px * t * s))
                if 0 <= sy < H and 0 <= sx < W and street[sy, sx]:
                    ok = True
            if not ok:
                break
            wcells += 1
        width = max(2.6, min(wcells * res, 8.0))            # CI-8 side-stub band
        treads = max(3, int(round(rise / RISER)))
        run = max(2.2, treads * GOING)
        sites.append({
            'x': round(x * res, 2), 'y': round(y * res, 2),
            'w': round(width, 2), 'run': round(run, 2),
            'ux': round(ux, 4), 'uy': round(uy, 4),
            'treads': treads,
            'from': lo, 'to': hi, 'rise_m': round(rise, 2),
        })
    return sites


def morph(mask, r, grow=True):
    """Binary dilate/erode by a disc of radius r cells. Pure numpy."""
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            sh = np.roll(np.roll(mask, dy, 0), dx, 1)
            out = (out | sh) if grow else (out & sh)
    return out


def blocks(built, lvl, res, close_m=2.6, street=None):
    """MA-5: no freestanding mass; Octopath closes a street with a CONTINUOUS
    built wall, not discrete boxes. OSM maps each dwelling separately, so 140
    separate polygons is a data artifact, not the physical fact - these houses
    share party walls. Close the gaps, trace the resulting blocks, and the town
    gets street walls instead of a field of sheds.

    A block is split where it crosses a terrace, because one mass cannot sit on
    two levels."""
    r = max(1, int(round(close_m / res)))
    closed = morph(morph(built, r, True), r, False)
    # THE RIBBON BUG: closing by 2.6 m bridges straight over the 2-3 m stepped
    # alleys that actually cut a hill town into blocks, so every contour band
    # merged into one 100 m strip and the map rendered as corrugation. The
    # street network already knows where the alleys are - cut them back out.
    if street is not None:
        closed = closed & ~street
    out = []
    for L in range(int(lvl.max()) + 1):
        m = closed & (lvl == L)
        if m.sum() < 40:
            continue
        for loop in clean_loops(m, res, eps_m=1.6, min_area_m2=40.0):
            out.append({'pts': loop, 'level': L})
    return out


def split_long(blk, max_len_m, gap_m=2.6):
    """Cut an over-long block into buildable lengths across its long axis,
    leaving a real alley gap between the pieces."""
    poly = [tuple(p) for p in blk['pts']]
    if len(poly) < 3:
        return [blk]
    best = None
    for deg in range(0, 90, 5):
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        xs = [p[0] * c + p[1] * s for p in poly]
        ys = [-p[0] * s + p[1] * c for p in poly]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if best is None or w * h < best[0]:
            best = (w * h, a, min(xs), max(xs), min(ys), max(ys))
    _, a, x0, x1, y0, y1 = best
    w, h = x1 - x0, y1 - y0
    L = max(w, h)
    if L <= max_len_m:
        return [blk]
    n = int(math.ceil(L / max_len_m))
    c, s = math.cos(a), math.sin(a)

    def back(u, v):
        return (u * c - v * s, u * s + v * c)

    out = []
    for i in range(n):
        lo = (L / n) * i + (gap_m / 2 if i else 0.0)
        hi = (L / n) * (i + 1) - (gap_m / 2 if i < n - 1 else 0.0)
        if w >= h:
            corners = [(x0 + lo, y0), (x0 + hi, y0), (x0 + hi, y1), (x0 + lo, y1)]
        else:
            corners = [(x0, y0 + lo), (x1, y0 + lo), (x1, y0 + hi), (x0, y0 + hi)]
        out.append({'pts': [list(back(u, v)) for u, v in corners],
                    'level': blk['level']})
    return out


def build(spec_dir):
    g = np.load(os.path.join(spec_dir, 'grids.npz'))
    spec = json.load(open(os.path.join(spec_dir, 'spec.json')))
    res, step, k = spec['res'], spec['level_step_m'], spec['levels']
    lvl, walk, street = g['lvl'], g['walk'], g['street']
    water, drops, quay = g['water'], g['drops'], g['quay']
    land = lvl >= 0

    terraces = []
    for L in range(k):
        loops = clean_loops((lvl >= L) & land, res)
        terraces.append({'level': L, 'z': round(L * step, 3), 'loops': loops})
        print(f'  level {L}: {len(loops)} terrace loops, '
              f'{sum(len(p) for p in loops)} vertices')

    # Streets as their own SURFACE, per level. Octopath never shows one uniform
    # ground - there is a cobbled way, a kerb, then the building base. Without
    # this the whole map is a single plane with sheds standing on it.
    ways_by_level = []
    for L in range(k):
        m = walk & (lvl == L)
        m = morph(morph(m, 1, True), 1, False)
        if m.sum() < 30:
            continue
        loops = clean_loops(m, res, eps_m=1.4, min_area_m2=30.0)
        if loops:
            ways_by_level.append({'level': L, 'loops': loops})
    print(f'  street surfaces: {sum(len(w["loops"]) for w in ways_by_level)} '
          f'across {len(ways_by_level)} levels')

    blk = blocks(g['built'], lvl, res, street=street)
    # MA-6: a footprint is square-ish or bar-shaped, never a 100 m ribbon. Any
    # block still longer than ~34 m gets a cross-alley cut, because a real town
    # has them and a 100 m unbroken mass is the single loudest wrong note.
    blk = [b for chunk in (split_long(b, 34.0) for b in blk) for b in chunk]
    print(f'  blocks: {len(blk)} party-wall masses '
          f'(from {int(g["built"].sum())} built cells)')

    out = {
        'res': res, 'level_step_m': step, 'levels': k, 'span_m': spec['span_m'],
        'terraces': terraces,
        'ways': ways_by_level,
        'blocks': blk,
        'parapets': runs_from_mask(drops, res),
        'quays': runs_from_mask(quay & ~drops, res),
        'stairs': stair_sites(lvl, street, walk, res, step),
        'shore': clean_loops(land, res, eps_m=2.0, min_area_m2=200.0),
    }
    p = os.path.join(spec_dir, 'geom.json')
    json.dump(out, open(p, 'w'))
    print(f'  parapet runs {len(out["parapets"])}, quay runs {len(out["quays"])}, '
          f'stairs {len(out["stairs"])}')
    print('  ->', p)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', default='place/villefranche/spec')
    a = ap.parse_args()
    build(a.spec)
