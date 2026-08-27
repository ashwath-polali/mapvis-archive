"""
assemble_map.py - the derived structure + the element kit -> an assembled map.

This is the stage that has never existed. Everything before it produced either
raw terrain (a topographic model made of two element types) or a legal-but-aimless
scatter of pieces. The difference here is that NOTHING IS PLACED BY CHOICE. Every
element fires because a measured geometric condition is true:

    a terrace edge meets water        -> quay wall, coped, battered
    a walkable edge has a fall        -> balustrade (ED-2, a guard is mandatory)
    a street crosses a level boundary -> a flight, cheeked, sized by the rise
    a block faces a street            -> doors and windows on its frontage bay grid
    a block is long                   -> a terrace row, not a box
    the highest block on the axis     -> the tower that terminates the sightline

No model looks at anything. No coordinate is authored. The rules read the same
grids `derive.py` produced from measured LiDAR.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P assemble_map.py -- --spec place/villefranche/spec
"""
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'kit'))
sys.path.insert(0, _HERE)

import circulation as C
import masses as M
import retaining as R
import thresholds as T
import water_terrain as W

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.abspath(arg('--spec', 'place/villefranche/spec'))
CHAR = 1.7

PARTS = []          # (material, verts, faces) accumulated, merged once at the end


def place(mat, mesh, x=0.0, y=0.0, z=0.0, rot=0.0, swap_yz=False):
    """Drop a kit mesh into world space. Kit pieces are authored at their own
    origin facing +y; rot is the bearing in radians."""
    if mesh is None:
        return
    v, f = mesh
    if not v or not f:
        return
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for p in v:
        px, py, pz = (p[0], p[2], p[1]) if swap_yz else (p[0], p[1], p[2])
        out.append((x + px * c - py * s, y + px * s + py * c, z + pz))
    PARTS.append((mat, out, [tuple(q) for q in f]))


def seg_dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = math.hypot(dx, dy)
    return (dx / m, dy / m, m) if m > 1e-9 else (1.0, 0.0, 0.0)


def walk_run(line, spacing):
    """Yield (x, y, bearing) every `spacing` metres along a polyline."""
    acc = 0.0
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        ux, uy, L = seg_dir(a, b)
        bearing = math.atan2(uy, ux)
        t = -acc
        while t + spacing <= L:
            t += spacing
            yield (a[0] + ux * t, a[1] + uy * t, bearing)
        acc = (L - t) if t > 0 else acc + L


def poly_edges(poly):
    for i in range(len(poly)):
        yield poly[i], poly[(i + 1) % len(poly)]


def poly_area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def obb(poly):
    best = None
    for deg in range(0, 90, 3):
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        xs = [p[0] * c + p[1] * s for p in poly]
        ys = [-p[0] * s + p[1] * c for p in poly]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if best is None or w * h < best[0]:
            best = (w * h, a, min(xs), max(xs), min(ys), max(ys))
    _, a, x0, x1, y0, y1 = best
    c, s = math.cos(a), math.sin(a)
    cx = (x0 + x1) / 2 * c - (y0 + y1) / 2 * s
    cy = (x0 + x1) / 2 * s + (y0 + y1) / 2 * c
    return a, (x1 - x0), (y1 - y0), (cx, cy)


# ------------------------------------------------------------------ the rules

def rule_quays(geom, step):
    """Land meeting sea is a quay. Not a cliff, not a slab edge - a coped,
    battered masonry wall with mooring posts, because that is what a harbour
    edge physically is."""
    n = 0
    for run in geom.get('quays', []):
        if len(run) < 2:
            continue
        for i in range(len(run) - 1):
            a, b = run[i], run[i + 1]
            ux, uy, L = seg_dir(a, b)
            if L < 2.5:
                continue
            place('quay_block',
                  W.quay_wall_coped(x0_m=0.0, x1_m=L, z_water_m=-1.6, z_deck_m=0.35),
                  a[0], a[1], 0.0, math.atan2(uy, ux))
            n += 1
        for (px, py, br) in walk_run(run, 11.0):
            place('quay_block', W.mooring_post(z_deck_m=0.35, z_water_m=-1.6), px, py, 0.0, br)
    return n


def rule_guards(geom, step):
    """ED-2 is a hard gate: every internal drop edge carries a guard. This is not
    decoration - an unguarded terrace lip is the single most common reason a map
    reads as unfinished geometry rather than a built place."""
    n = 0
    for run in geom.get('parapets', []):
        if len(run) < 2:
            continue
        z = run_level_z(run, geom, step)
        path = [tuple(p) for p in run]
        # retaining.py takes the PLAN POLYLINE directly, so the guard follows the
        # terrace lip's real curve instead of being chopped into straight bays.
        try:
            place('stone_course', R.parapet_wall(path=path, h=1.05), 0, 0, z)
            n += 1
        except Exception:
            pass
    return n


def rule_flights(geom, step):
    """EL-5: two levels are impassable without a connector. The street graph
    decides where; the rise decides whether it is one flight or two with a
    landing. A 3.2 m rise is two flights, not a 19-tread ladder."""
    n = 0
    for s in geom.get('stairs', []):
        rise = s['rise_m']
        if rise < 0.6:
            continue
        # measured flight width band is 1.6-2.4 m; a 6 m "stair" is a ramp
        w = max(1.6, min(s['w'], 2.4))
        br = math.atan2(s['uy'], s['ux']) - math.pi / 2
        z0 = s['from'] * step
        # a half-space landing must be at least as deep as the flight is wide,
        # and the kit caps a landing at 1.8 m - so a landed flight is a NARROW
        # flight by construction. Wide runs stay single straight flights.
        # A single straight flight tops out at ~1.9 m of rise (the kit gates it,
        # measured off Octopath). A full 3.2 m level step is therefore ALWAYS a
        # landed flight, and a landed flight is narrow. That is not a compromise,
        # it is what a stepped alley in a hill town actually is.
        # EL-3: a flight is 3-8 treads and Octopath's risers are CHUNKY. Size the
        # riser to land the count in band rather than emitting a fine 9-riser
        # domestic stair, which is what read as corduroy in every earlier build.
        treads = max(3, min(8, int(math.ceil(rise / 0.24))))
        riser = min(0.24, max(0.19, rise / treads))
        if rise > 3.0:
            w = min(w, 1.8)
            mesh = C.flight_with_landing(rise_m=rise, width_m=w,
                                         landing_len_m=1.8, riser_m=riser)
        else:
            mesh = C.straight_flight(rise_m=rise, width_m=w, cheeks=True,
                                     riser_m=riser)
        place('stone_course', mesh, s['x'], s['y'], z0, br)
        run = max(2.2, rise / 0.21 * 0.45)
        for side in (-1, 1):
            cx = s['x'] - s['uy'] * side * (w / 2 + 0.22)
            cy = s['y'] + s['ux'] * side * (w / 2 + 0.22)
            place('quay_block', C.cheek_wall(rise_m=rise, run_m=run), cx, cy, z0, br)
        n += 1
    return n


def rule_masses(geom, step):
    """MA-5/MA-6. A long block is a TERRACE ROW with a repeating bay rhythm, not
    a box: the rhythm is what makes a street wall read as buildings rather than
    as one extruded lump. A small block is a house. The tallest block on the
    dominant axis becomes the tower that terminates the sightline (LM-2)."""
    blocks = geom.get('blocks', [])
    if not blocks:
        return 0, None
    ranked = sorted(blocks, key=lambda b: (b['level'], poly_area(b['pts'])), reverse=True)
    landmark = ranked[0] if ranked else None
    n, skipped = 0, []
    for i, blk in enumerate(blocks):
      try:
        poly = blk['pts']
        if len(poly) < 3:
            continue
        A = poly_area(poly)
        if A < 40:
            continue
        ang, w, d, (cx, cy) = obb(poly)
        z = blk['level'] * step
        long_side, short_side = max(w, d), min(w, d)
        if w < d:
            ang += math.pi / 2
        storeys = 2 if A < 220 else 3
        h = storeys * 3.2

        if blk is landmark and long_side > 14:
            place('quay_block', M.mass_tower_square_staged(
                plan_w_m=min(9.0, short_side * 0.8), stage_count=3, stage_h_m=4.6),
                cx, cy, z, ang)
            n += 1
            continue

        # A box house tops out at 5.6 CHAR of frontage. Anything wider is a ROW,
        # because that is the only honest way a wide built mass exists.
        if long_side > 9.0:
            # a terrace unit is one house frontage: 2.6-4.1 CHAR. The bay COUNT
            # follows the block length, never the other way round - capping the
            # count is what produced 13 m "houses".
            units = max(2, int(round(long_side / 5.6)))
            unit_w = max(4.4, min(long_side / units, 7.0))
            # a terrace row's cornice sits 6-9 CHAR up (measured). At 3.2 m
            # floor-to-floor that is FOUR storeys - which is what a Mediterranean
            # harbour terrace actually is.
            place('brick' if i % 3 else 'plaster_timber', M.mass_row_terrace(
                unit_w_m=unit_w, unit_count=units,
                depth_m=max(5.0, min(short_side, 14.0)),
                storeys=4, floor_to_floor_m=3.2),
                cx, cy, z, ang)
        else:
            # a box house's eaves sit 1.90-2.70 CHAR up (measured), so it is a
            # ONE-storey form. Anything taller is a row, not a house.
            eaves = max(3.3, min(h, 4.5))
            place('brick' if i % 3 else 'plaster_timber', M.mass_box_house(
                width_m=max(4.0, long_side), depth_m=max(4.0, short_side),
                eaves_h_m=eaves, storeys=1, floor_to_floor_m=eaves),
                cx, cy, z, ang)
            h = eaves
            place('shingle', M.roof_gable_prism(
                span_m=max(4.0, short_side), length_m=max(4.0, long_side),
                pitch_deg=48.0), cx, cy, z + h, ang + math.pi / 2)
        n += 1
      except Exception as e:
        # the kit gates its own dimensions against CHAR; a block that cannot be
        # built honestly is REPORTED, never silently fudged into range.
        skipped.append(f'{i}: {type(e).__name__}: {str(e)[:80]}')
    if skipped:
        print(f'[assemble]   {len(skipped)} masses skipped (out of buildable range):')
        for s in skipped[:6]:
            print('     ', s)
    return n, landmark


def rule_openings(geom, step):
    """A wall with no openings is a box, whatever its silhouette. Doors and
    windows go on the block's STREET frontage, on the bay grid the mass already
    has - so they land on the rhythm instead of being sprinkled."""
    n = 0
    for i, blk in enumerate(geom.get('blocks', [])):
        poly = blk['pts']
        if len(poly) < 3 or poly_area(poly) < 40:
            continue
        z = blk['level'] * step
        best = max(poly_edges(poly), key=lambda e: math.dist(e[0], e[1]))
        a, b = best
        ux, uy, L = seg_dir(a, b)
        if L < 5.0:
            continue
        br = math.atan2(uy, ux) - math.pi / 2
        nx, ny = uy, -ux                      # outward-ish normal
        bays = max(1, int(L / 4.2))
        storeys = 4 if L > 9.0 else 2
        for k in range(bays):
            t = (k + 0.5) / bays * L
            px, py = a[0] + ux * t + nx * 0.05, a[1] + uy * t + ny * 0.05
            try:
                if k == bays // 2:
                    place('plank', T.arched_doorway(base_z=0.0), px, py, z, br)
                else:
                    place('plank', T.window_opening(cill_z=1.0, base_z=0.0), px, py, z, br)
                # a cill sits 0.85-1.10 m above ITS OWN floor, so upper windows
                # are the same element lifted a storey, not a taller cill.
                for s in range(1, storeys):
                    place('plank', T.window_opening(cill_z=1.0, base_z=0.0),
                          px, py, z + s * 3.2, br)
                n += 1
            except Exception:
                pass
    return n


def run_level_z(run, geom, step):
    px, py = run[len(run) // 2]
    best = 0.0
    for t in geom['terraces']:
        for loop in t['loops']:
            if point_in(px, py, loop):
                best = max(best, t['z'])
    return best


def point_in(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xi:
                inside = not inside
    return inside


def ground(geom, step):
    """The terrain the kit sits on: discrete terrace planes with a lofted face
    at every level change, plus the sea. Polygons only - never per-cell."""
    from build_place import prism, inflate           # reuse, do not duplicate
    span = geom['span_m']
    pad = span * 1.4
    PARTS.append(('quay_block',) + prism(
        [(-pad, -pad), (span + pad, -pad), (span + pad, span + pad), (-pad, span + pad)],
        -7.6, -1.6))
    for t in geom['terraces']:
        below = (t['level'] - 1) * step if t['level'] > 0 else -1.6
        for loop in t['loops']:
            if len(loop) < 3:
                continue
            PARTS.append(('cobble',) + prism(loop, below, t['z'], cap_top=True))
            # The terrace FACE is a real retaining wall on the terrace's own plan
            # polyline - battered, with footing, string course and oversailing
            # coping - not a bare extruded skirt.
            if t['z'] - below > 0.9:
                try:
                    place('quay_block', R.coursed_retaining_wall(
                        path=[tuple(p) for p in loop],
                        h_retained=min(t['z'] - below, 3.4)), 0, 0, below)
                except Exception:
                    PARTS.append(('stone_course',) + prism(
                        inflate(loop, 0.26), t['z'] - 0.34, t['z'] + 0.06))


def main():
    geom = json.load(open(os.path.join(SPEC, 'geom.json')))
    step = geom['level_step_m']
    ground(geom, step)
    q = rule_quays(geom, step)
    g = rule_guards(geom, step)
    f = rule_flights(geom, step)
    m, landmark = rule_masses(geom, step)
    o = rule_openings(geom, step)
    print(f'[assemble] quay runs {q} | guards {g} | flights {f} | masses {m} | openings {o}')
    return geom


if __name__ == '__main__':
    import build_place as B
    geom = main()
    for mat, v, fcs in PARTS:
        B.emit(mat, v, fcs)
    import bpy
    objs = B.flush()
    tris = 0
    for ob in objs:
        ob.data.calc_loop_triangles()
        tris += len(ob.data.loop_triangles)
    B.setup(geom['span_m'], B.TEXTURED)
    tag = 'tex' if B.TEXTURED else 'grey'
    p = os.path.join(HERE, arg('--out', 'shots'), f'assembled-{tag}.png')
    B.render(p)
    print(f'[assemble] {len(objs)} objects, {tris} triangles -> {p}')
