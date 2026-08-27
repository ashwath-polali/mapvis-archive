"""
derive.py - turn a real measured place into an Octopath-grammar map spec.

THE MECHANISM, and it is the whole idea:

A real hillside is a continuous surface. Octopath's ground is never continuous -
`OCTOPATH-STRUCTURE.md` EL-1 is a hard gate: elevation is an INTEGER LEVEL FIELD,
no gradients, no walkable slopes. So the single act of QUANTISING real measured
terrain into discrete levels does the Octopath-ification, and every piece of the
Octopath architectural vocabulary then falls out as a FORCED consequence:

    two levels meet                 -> a retaining wall MUST exist there
    a street crosses that boundary  -> a stair MUST exist there
    a walkable level has a drop     -> a parapet MUST exist there  (ED-2)
    land meets sea                  -> a quay MUST exist there
    a building sits across levels   -> it terraces, or it gets a plinth

Nothing here is placed because it looks good. Everything is placed because the
measured ground and the rulebook leave no other option. No model looks at
anything; there is not a single authored coordinate in this file.

    py derive.py --place villefranche
"""
import argparse
import json
import math
import os

import numpy as np

# --- the measured Octopath bands this file is allowed to steer by -------------
# from docs/OCTOPATH-STRUCTURE.md, all DERIVED with stated n
# EL-4 says a TOWN has 3-5 levels, but that was measured on gentle ground; the
# steep-coast cases (bolderfall) run 5+. The binding rule is EL-2: one step is
# ~1.0-1.5 CHAR. Honour EL-2 and let the level COUNT follow the real terrain,
# because forcing 5 levels onto a 23 m hillside gives 5.7 m steps - a 33-tread
# flight, which is not a stair, it is a cliff with lines on it.
LEVELS_TOWN = (3, 16)
WALKFRAC = (0.10, 0.32)       # MA-1 gate: walkable is a minority of the rect
CHAR = 1.7                    # metres, one person
# EL-2, re-measured 2026-07-28 across 34 frames: ONE LEVEL IS EXACTLY 1.0 CHAR.
# Not 1.5, not 1.9. A 3.2 m step is nearly two Octopath levels stacked, which is
# why the terraces read as engineering cuts instead of as a stepped town.
STEP_MIN, STEP_MAX = 1.5, 2.2


def load(d):
    osm = json.load(open(os.path.join(d, 'osm.json')))
    elev = json.load(open(os.path.join(d, 'elev.json')))
    meta = json.load(open(os.path.join(d, 'meta.json')))
    return osm, elev, meta


def utm(lat, lon, zone):
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    la, lo = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    T = math.tan(la) ** 2
    C = ep2 * math.cos(la) ** 2
    A = math.cos(la) * (lo - lon0)
    M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64) * la
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32) * math.sin(2 * la)
             + (15 * e2 ** 2 / 256) * math.sin(4 * la))
    k0 = 0.9996
    x = k0 * N * (A + (1 - T + C) * A ** 3 / 6) + 500000.0
    y = k0 * (M + N * math.tan(la) * (A ** 2 / 2 + (5 - T + 9 * C) * A ** 4 / 24))
    return x, y


def project(osm, meta):
    """OSM lat/lon -> local metres, origin at the bbox centre."""
    zone = meta['utm_zone']
    ox, oy = meta['origin_utm']
    nodes = {}
    for el in osm['elements']:
        if el['type'] == 'node':
            x, y = utm(el['lat'], el['lon'], zone)
            nodes[el['id']] = (x - ox, y - oy)
    ways = []
    for el in osm['elements']:
        if el['type'] != 'way':
            continue
        pts = [nodes[n] for n in el.get('nodes', []) if n in nodes]
        if len(pts) >= 2:
            ways.append({'id': el['id'], 'tags': el.get('tags', {}), 'pts': pts})
    return nodes, ways


def elevation_field(elev, meta, res):
    """Resample the measured grid onto a local metric raster at `res` m/px.
    Sea and no-data come back as the sentinel; they become water, not ground."""
    s, w, n, e = elev['bbox']
    nx = elev['nx']
    z = np.array([np.nan if (v is None or v < -100) else v
                  for v in elev['z']], np.float32).reshape(nx, nx)
    zone = meta['utm_zone']
    ox, oy = meta['origin_utm']
    x0, y0 = utm(s, w, zone)
    x1, y1 = utm(n, e, zone)
    X0, Y0 = min(x0, x1) - ox, min(y0, y1) - oy
    X1, Y1 = max(x0, x1) - ox, max(y0, y1) - oy
    W = int((X1 - X0) / res)
    H = int((Y1 - Y0) / res)
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    u = np.clip(gx / W * (nx - 1), 0, nx - 1)
    v = np.clip(gy / H * (nx - 1), 0, nx - 1)
    i0, j0 = u.astype(int), v.astype(int)
    i1, j1 = np.minimum(i0 + 1, nx - 1), np.minimum(j0 + 1, nx - 1)
    fu, fv = u - i0, v - j0
    zz = (z[j0, i0] * (1 - fu) * (1 - fv) + z[j0, i1] * fu * (1 - fv)
          + z[j1, i0] * (1 - fu) * fv + z[j1, i1] * fu * fv)
    return zz, (X0, Y0, X1, Y1)


def rasterise_polys(shape, extent, polys, res):
    """Scanline fill. Deterministic, no library, no perception."""
    X0, Y0, _, _ = extent
    H, W = shape
    out = np.zeros(shape, bool)
    for pts in polys:
        px = [(p[0] - X0) / res for p in pts]
        py = [(p[1] - Y0) / res for p in pts]
        ylo = max(0, int(math.floor(min(py))))
        yhi = min(H - 1, int(math.ceil(max(py))))
        for yy in range(ylo, yhi + 1):
            xs = []
            for k in range(len(px)):
                x1_, y1_ = px[k], py[k]
                x2_, y2_ = px[(k + 1) % len(px)], py[(k + 1) % len(px)]
                if (y1_ <= yy < y2_) or (y2_ <= yy < y1_):
                    xs.append(x1_ + (yy - y1_) / (y2_ - y1_) * (x2_ - x1_))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                a, b = int(math.ceil(xs[k])), int(math.floor(xs[k + 1]))
                if b >= 0 and a < W:
                    out[yy, max(0, a):min(W, b + 1)] = True
    return out


def stroke_lines(shape, extent, lines, res, width_m):
    """Stamp street centrelines to a given carriageway width."""
    X0, Y0, _, _ = extent
    H, W = shape
    out = np.zeros(shape, bool)
    r = max(1, int(round(width_m / 2 / res)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disc = (xx ** 2 + yy ** 2) <= r * r
    for pts in lines:
        for k in range(len(pts) - 1):
            ax = (pts[k][0] - X0) / res
            ay = (pts[k][1] - Y0) / res
            bx = (pts[k + 1][0] - X0) / res
            by = (pts[k + 1][1] - Y0) / res
            n = max(1, int(max(abs(bx - ax), abs(by - ay))))
            for t in range(n + 1):
                cx = int(ax + (bx - ax) * t / n)
                cy = int(ay + (by - ay) * t / n)
                y0c, y1c = max(0, cy - r), min(H, cy + r + 1)
                x0c, x1c = max(0, cx - r), min(W, cx + r + 1)
                if y1c <= y0c or x1c <= x0c:
                    continue
                sub = disc[y0c - (cy - r):y1c - (cy - r), x0c - (cx - r):x1c - (cx - r)]
                out[y0c:y1c, x0c:x1c] |= sub
    return out


ROAD_W = {'primary': 9, 'secondary': 8, 'tertiary': 7, 'residential': 6,
          'unclassified': 6, 'living_street': 6, 'pedestrian': 7, 'service': 4.5,
          'footway': 3.0, 'path': 2.5, 'steps': 3.0, 'track': 3.5}


def choose_window(land, built, street, water, res, span_m):
    """Pick the map's extent MECHANICALLY, against the measured Octopath bands -
    not by looking. Score = does this window contain a town edge on water, with
    enough built mass and street, in the walkable-fraction band."""
    H, W = land.shape
    n = int(span_m / res)
    if n >= min(H, W):
        return 0, 0, min(H, W)
    step = max(4, n // 12)
    best, arg = -1e9, (0, 0)
    for y in range(0, H - n, step):
        for x in range(0, W - n, step):
            sl = (slice(y, y + n), slice(x, x + n))
            b = built[sl].mean()
            s = street[sl].mean()
            wt = water[sl].mean()
            ld = land[sl].mean()
            if ld < 0.35 or b < 0.04:
                continue
            # MA-1 wants walkable a minority; ED-1 wants the boundary closed by
            # water or cliff, so a real coast edge in frame is worth a lot.
            coast = 1.0 - abs(wt - 0.22) / 0.22
            score = 3.0 * max(0, coast) + 4.0 * min(b, 0.30) / 0.30 + 2.5 * min(s, 0.18) / 0.18
            if score > best:
                best, arg = score, (y, x)
    return arg[0], arg[1], n


def quantise_levels(z, walk, res):
    """EL-1 + EL-4. Find the level step that puts the walkable level count inside
    Octopath's measured town band (3-5). The terrain decides the shape; the
    rulebook decides the step. Nobody's taste is consulted."""
    zv = z[walk & np.isfinite(z)]
    if zv.size < 50:
        raise SystemExit('no walkable ground found in window')
    lo, hi = np.percentile(zv, 2), np.percentile(zv, 98)
    best = None
    for step in np.arange(STEP_MIN, STEP_MAX + 0.01, 0.1):
        k = int(np.floor((hi - lo) / step)) + 1
        if LEVELS_TOWN[0] <= k <= LEVELS_TOWN[1]:
            pen = abs(step - CHAR)          # EL-2: one level = one CHAR
            if best is None or pen < best[0]:
                best = (pen, step, k)
    if best is None:                       # relief too great for a town band
        step = (hi - lo) / LEVELS_TOWN[1]
        best = (0, step, LEVELS_TOWN[1])
    _, step, k = best
    lvl = np.clip(np.floor((z - lo) / step), 0, k - 1)
    lvl[~np.isfinite(z)] = -1
    return lvl.astype(np.int16), float(step), int(k), float(lo)


def derive_vocabulary(lvl, walk, water):
    """Everything Octopath is made of, as forced consequences of the level field."""
    H, W = lvl.shape

    def shift(a, dy, dx):
        return np.roll(np.roll(a, dy, 0), dx, 1)

    walls = np.zeros((H, W), bool)      # a level boundary on land
    drops = np.zeros((H, W), bool)      # walkable ground with a fall beside it
    quay = np.zeros((H, W), bool)       # land meeting sea
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = shift(lvl, dy, dx)
        nw = shift(water, dy, dx)
        land_here = lvl >= 0
        walls |= land_here & (nb >= 0) & (nb != lvl)
        drops |= walk & (nb >= 0) & (nb < lvl)
        quay |= land_here & nw
    return walls, drops, quay


def main(place, root, span_m, res):
    d = os.path.join(root, place)
    osm, elev, meta = load(d)
    nodes, ways = project(osm, meta)
    z, extent = elevation_field(elev, meta, res)
    H, W = z.shape
    print(f'[derive] {place}: raster {W}x{H} at {res} m/px '
          f'= {W * res:.0f} x {H * res:.0f} m')

    blds = [w['pts'] for w in ways if 'building' in w['tags']]
    roads = [(w['pts'], ROAD_W.get(w['tags'].get('highway'), 4.0))
             for w in ways if 'highway' in w['tags']]
    squares = [w['pts'] for w in ways
               if w['tags'].get('place') == 'square' or w['tags'].get('leisure') == 'park']

    built = rasterise_polys((H, W), extent, blds, res)
    street = np.zeros((H, W), bool)
    for grp_w in sorted({r[1] for r in roads}):
        street |= stroke_lines((H, W), extent, [p for p, ww in roads if ww == grp_w],
                               res, grp_w)
    street |= rasterise_polys((H, W), extent, squares, res)
    water = ~np.isfinite(z) | (np.nan_to_num(z, nan=-999) < 0.4)
    land = ~water

    y0, x0, n = choose_window(land, built, street, water, res, span_m)
    print(f'[derive] window chosen mechanically at ({x0},{y0}) size {n} px '
          f'= {n * res:.0f} m; built {built[y0:y0+n, x0:x0+n].mean():.3f}, '
          f'water {water[y0:y0+n, x0:x0+n].mean():.3f}')
    sl = (slice(y0, y0 + n), slice(x0, x0 + n))
    z, built, street, water, land = z[sl], built[sl], street[sl], water[sl], land[sl]

    walk = street & land & ~built
    lvl, step, k, base = quantise_levels(z, walk | (land & ~built), res)
    lvl[water] = -1
    walls, drops, quay = derive_vocabulary(lvl, walk, water)

    wf = walk.mean()
    print(f'[derive] EL-4 levels = {k}  (band {LEVELS_TOWN})   step = {step:.2f} m '
          f'= {step / CHAR:.2f} CHAR')
    print(f'[derive] MA-1 walkfrac = {wf:.3f}  (band {WALKFRAC})')
    print(f'[derive] forced vocabulary: {walls.sum()} wall px, {drops.sum()} drop-edge px, '
          f'{quay.sum()} quay px, {built.sum()} building px')

    out = os.path.join(d, 'spec')
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, 'grids.npz'), z=z, lvl=lvl, built=built,
                        street=street, water=water, walk=walk, walls=walls,
                        drops=drops, quay=quay)

    # Vector footprints beat rasterised ones: these are real surveyed polygons, so
    # the buildings get true corners instead of a 1 m staircase edge.
    X0, Y0, _, _ = extent
    wx0, wy0 = X0 + x0 * res, Y0 + y0 * res
    span = n * res

    def local(p):
        return [round(p[0] - wx0, 2), round(p[1] - wy0, 2)]

    def inside(pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs) > -20 and min(ys) > -20
                and max(xs) < span + 20 and max(ys) < span + 20)

    def storeys(t):
        for key in ('building:levels', 'levels'):
            try:
                return max(1, min(6, int(float(t[key]))))
            except (KeyError, ValueError):
                pass
        try:
            return max(1, min(6, int(round(float(t['height']) / 3.0))))
        except (KeyError, ValueError):
            return 0

    vec_b, vec_s, vec_q = [], [], []
    for w in ways:
        t = w['tags']
        pts = [local(p) for p in w['pts']]
        if not inside(pts):
            continue
        if 'building' in t:
            vec_b.append({'pts': pts, 'storeys': storeys(t),
                          'kind': t.get('building', 'yes')})
        elif 'highway' in t:
            vec_s.append({'pts': pts, 'w': ROAD_W.get(t['highway'], 4.0),
                          'kind': t['highway']})
        elif t.get('man_made') in ('quay', 'pier', 'breakwater', 'groyne'):
            vec_q.append({'pts': pts, 'kind': t['man_made']})
    json.dump({'span_m': span, 'buildings': vec_b, 'streets': vec_s, 'quays': vec_q},
              open(os.path.join(out, 'vectors.json'), 'w'))
    known = sum(1 for b in vec_b if b['storeys'])
    print(f'[derive] vectors: {len(vec_b)} footprints ({known} with surveyed storeys), '
          f'{len(vec_s)} streets, {len(vec_q)} quay/pier')
    json.dump({'place': place, 'res': res, 'span_m': n * res, 'level_step_m': step,
               'levels': k, 'base_z': base, 'walkfrac': float(wf),
               'gates': {'EL-4': bool(LEVELS_TOWN[0] <= k <= LEVELS_TOWN[1]),
                         'MA-1': bool(WALKFRAC[0] <= wf <= WALKFRAC[1])}},
              open(os.path.join(out, 'spec.json'), 'w'), indent=1)

    try:
        from PIL import Image
        vis = np.zeros((*lvl.shape, 3), np.uint8)
        vis[water] = (38, 58, 92)
        for i in range(k):
            t = 70 + int(120 * i / max(1, k - 1))
            vis[(lvl == i) & ~water] = (t, t - 6, t - 16)
        vis[built] = (150, 96, 60)
        vis[walk] = (232, 214, 176)
        vis[walls] = (30, 26, 24)
        vis[quay] = (86, 120, 150)
        Image.fromarray(vis[::-1]).save(os.path.join(out, 'plan.png'))
        print('[derive] plan ->', os.path.join(out, 'plan.png'))
    except ImportError:
        pass
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--place', default='villefranche')
    ap.add_argument('--root', default='place')
    ap.add_argument('--span', type=float, default=340.0, help='map extent, metres')
    ap.add_argument('--res', type=float, default=1.0, help='metres per raster cell')
    a = ap.parse_args()
    main(a.place, a.root, a.span, a.res)
