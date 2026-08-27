"""
assemble_solid.py - the SUBTRACTIVE assembler. Carve the void out of one solid.

This replaces the additive assembler, and the reason is the central finding of
docs/THE-PICTURE.md: an Octopath map's composition is ABOUT THE VOID. A street is
a slot cut through one continuous mass, so a door is a hole in a wall you are
already touching. An arch is a hole you see water through. A dock is a notch cut
out of stone. A chamber is a gouge in rock.

The additive assembler could not express any of that. It extruded footprints and
placed kit pieces on top, which yields detached boxes with uniform gaps - a car
park with sheds on it, in that document's words. ops_solid.py was built with
carve / pierce / overhang / cantilever / undercroft / shelf_stack / two_level and
the additive assembler called NONE of them, so the whole operator library sat
dead next to a map that needed every line of it.

Order of operations, and each step is forced rather than chosen:

    1  one solid plate, the full extent, no holes
    2  CARVE the walk region out of it            -> streets are slots, fabric is
                                                     party-wall continuous by construction
    3  CARVE the water body out of it             -> a dock is a notch, not a gap
    4  PIERCE every frontage opening              -> real holes with reveals
    5  UNDERCROFT the terrace faces               -> the terrace is legibly held up
    6  CANTILEVER decks over the water edge       -> undersides and joists visible
    7  SHELF_STACK the non-walkable rim           -> 5-7 shelves, overhanging lips
    8  edge profiles over every horizontal edge   -> ops_edges, automatic

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P assemble_solid.py -- --spec place/harbour-town/spec
"""
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'kit'))
sys.path.insert(0, _HERE)

import _geom as G           # noqa: E402
import numpy as np          # noqa: E402
import ops_solid as OS      # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


CHAR = 1.7
LEVEL = 1.7
SEA_Z = -1.8
STOREY = 3.2


def contours(mask, res, eps=1.4, min_area=18.0):
    """Traced boundaries of a raster region, simplified. Reuses the tracer that
    already exists rather than adding a second one."""
    import vectorise as V
    return V.clean_loops(mask, res, eps_m=eps, min_area_m2=min_area)


def prism_mesh(loop, z0, z1, mat='stone'):
    """A CLOSED prism. G.prism emits coincident-but-distinct verts, so at a
    40 m scale the shell arrives with 22 boundary edges and ops_solid rightly
    refuses to CSG an open shell. Weld before handing it over - compose.py hit
    exactly this and its note says the fix belongs in the caller."""
    m = G.Mesh()
    G.prism(m, [(p[0], p[1]) for p in loop], z0, z1, mat=mat,
            cap_top=True, cap_bot=True)
    return weld(m)


def weld(mesh, tol=1e-4):
    q = 1.0 / tol
    key, remap, verts = {}, [], []
    for v in mesh.v:
        k = (round(v[0] * q), round(v[1] * q), round(v[2] * q))
        if k not in key:
            key[k] = len(verts)
            verts.append(tuple(float(x) for x in v))
        remap.append(key[k])
    out = G.Mesh()
    out.v = verts
    for f, mat in zip(mesh.f, mesh.m):
        nf = []
        for i in f:
            j = remap[i]
            if not nf or nf[-1] != j:
                nf.append(j)
        if len(nf) > 2 and nf[0] == nf[-1]:
            nf.pop()
        if len(nf) >= 3:
            out.f.append(tuple(nf))
            out.m.append(mat)
    return out


def build(spec, want=('carve', 'pierce', 'undercroft', 'cantilever', 'shelf')):
    geom = json.load(open(os.path.join(spec, 'geom.json')))
    grids = np.load(os.path.join(spec, 'grids.npz'))
    res = geom['res']
    step = geom['level_step_m']
    span = geom['span_m']
    lvl, walk, built = grids['lvl'], grids['walk'], grids['built']
    water = grids['water'] if 'water' in grids else np.zeros_like(walk)
    nlev = geom['levels']

    log = {}

    # ---- 1. ONE SOLID. The whole extent, to the top of the tallest fabric.
    top = (nlev - 1) * step + 4 * STOREY
    outline = [(0.0, 0.0), (span, 0.0), (span, span), (0.0, span)]
    solid = prism_mesh(outline, SEA_Z, top, mat='ashlar')
    v0 = abs(OS.volume(solid))
    log['solid_m3'] = round(v0, 1)

    # ---- 2. CARVE THE WALK REGION. Per level, so the cut floor lands on that
    # level's ground and the fabric above it survives as a party wall.
    if 'carve' in want:
        cut = 0
        for L in range(nlev):
            m = (walk & (lvl == L))
            if m.sum() < 12:
                continue
            for loop in contours(m, res, eps=1.2, min_area=14.0):
                if len(loop) < 3:
                    continue
                # cut from this level's floor up through everything above it
                tool = prism_mesh(loop, L * step, top + 1.0, mat='reveal')
                try:
                    solid = weld(OS.carve(solid, tool, tool_mat='reveal'))
                    cut += 1
                except Exception as e:
                    log.setdefault('carve_failures', []).append(str(e)[:70])
        log['streets_carved'] = cut
        log['after_streets_m3'] = round(abs(OS.volume(solid)), 1)

    # ---- 3. CARVE THE WATER. A basin is a NOTCH taken out of the stone, which is
    # what makes a harbour read as cut rather than as a gap left between things.
    if 'carve' in want and water.any():
        n = 0
        for loop in contours(water, res, eps=1.6, min_area=40.0):
            if len(loop) < 3:
                continue
            try:
                solid = weld(OS.carve(solid, prism_mesh(loop, SEA_Z - 2.0, top + 1.0,
                                                        mat='reveal'), tool_mat='reveal'))
                n += 1
            except Exception as e:
                log.setdefault('carve_failures', []).append(str(e)[:70])
        log['basins_carved'] = n
        log['after_water_m3'] = round(abs(OS.volume(solid)), 1)

    parts = [(f.get('mat', 'ashlar') if isinstance(f, dict) else 'ashlar',)
             for f in []]                      # placeholder, replaced below
    parts = mesh_to_parts(solid)

    # ---- 4. PIERCE the frontage. Real holes, not plaques stuck on a face.
    if 'pierce' in want:
        pierced = 0
        for blk in geom.get('blocks', [])[:int(arg('--max-pierce', 14))]:
            poly = [tuple(p) for p in blk['pts']]
            if len(poly) < 3:
                continue
            z = blk['level'] * step
            a, b = longest_edge(poly)
            ux, uy, L = seg(a, b)
            if L < 4.5:
                continue
            nx, ny = uy, -ux
            bays = max(1, int(L / 4.6))
            for k in range(bays):
                t = (k + 0.5) / bays * L
                cx, cy = a[0] + ux * t, a[1] + uy * t
                w, h, cill = (1.15, 2.25, 0.0) if k == bays // 2 else (0.95, 1.35, 1.0)
                op = opening_box(cx, cy, nx, ny, w, h, z + cill, depth=2.2)
                try:
                    solid = weld(OS.carve(solid, op, tool_mat='reveal'))
                    pierced += 1
                except Exception as e:
                    log.setdefault('pierce_failures', []).append(str(e)[:70])
        log['openings_pierced'] = pierced
        parts = mesh_to_parts(solid)

    # ---- 5/6/7. The things held in the air, which extrusion cannot make at all.
    extra = []
    if 'undercroft' in want:
        n = 0
        for run in geom.get('parapets', [])[:6]:
            if len(run) < 2:
                continue
            a, b = run[0], run[-1]
            ux, uy, L = seg(a, b)
            if L < 9.0:
                continue
            m = G.Mesh()
            OS.undercroft(span=min(L, 22.0), bays=max(2, int(L / 5.5)),
                          depth=4.0, clear_h=2.295, into=m)
            extra += place_mesh(m, a[0], a[1], LEVEL, math.atan2(uy, ux))
            n += 1
        log['undercrofts'] = n

    if 'cantilever' in want:
        n = 0
        for run in geom.get('quays', [])[:8]:
            if len(run) < 2:
                continue
            a, b = run[0], run[-1]
            ux, uy, L = seg(a, b)
            if L < 6.0:
                continue
            m = G.Mesh()
            OS.cantilever(reach=2.8, joists=max(4, int(L / 1.4)), into=m)
            extra += place_mesh(m, a[0], a[1], 0.4, math.atan2(uy, ux))
            n += 1
        log['cantilevers'] = n

    if 'shelf' in want:
        rim = (~walk) & (~built) & (lvl >= 0)
        n = 0
        for loop in contours(rim, res, eps=2.4, min_area=120.0)[:4]:
            if len(loop) < 3:
                continue
            m = G.Mesh()
            OS.shelf_stack(n=6, into=m)
            cx = sum(p[0] for p in loop) / len(loop)
            cy = sum(p[1] for p in loop) / len(loop)
            extra += place_mesh(m, cx, cy, 0.0, 0.0)
            n += 1
        log['shelf_stacks'] = n

    parts += extra
    return geom, parts, log


# ------------------------------------------------------------------ helpers

def mesh_to_parts(mesh):
    """Split a Mesh into (material, verts, faces) parts the renderer consumes."""
    bymat = {}
    for i, f in enumerate(mesh.f):
        mat = mesh.m[i] if i < len(mesh.m) else 'ashlar'
        bymat.setdefault(mat, []).append(f)
    out = []
    for mat, faces in bymat.items():
        idx, remap, V, F = 0, {}, [], []
        for f in faces:
            q = []
            for vi in f:
                if vi not in remap:
                    remap[vi] = len(V)
                    V.append(tuple(mesh.v[vi]))
                q.append(remap[vi])
            F.append(tuple(q))
        out.append((mat, V, F))
    return out


def place_mesh(mesh, x, y, z, rot):
    c, s = math.cos(rot), math.sin(rot)
    bymat = {}
    for i, f in enumerate(mesh.f):
        bymat.setdefault(mesh.m[i] if i < len(mesh.m) else 'stone', []).append(f)
    out = []
    for mat, faces in bymat.items():
        remap, V, F = {}, [], []
        for f in faces:
            q = []
            for vi in f:
                if vi not in remap:
                    p = mesh.v[vi]
                    remap[vi] = len(V)
                    V.append((x + p[0] * c - p[1] * s, y + p[0] * s + p[1] * c, z + p[2]))
                q.append(remap[vi])
            F.append(tuple(q))
        out.append((mat, V, F))
    return out


def seg(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return (dx / L, dy / L, L) if L > 1e-9 else (1.0, 0.0, 0.0)


def longest_edge(poly):
    best, out = -1, (poly[0], poly[1])
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = math.dist(a, b)
        if d > best:
            best, out = d, (a, b)
    return out


def opening_box(cx, cy, nx, ny, w, h, z, depth):
    """A tool solid for one opening: wide enough in the wall normal to cut clean
    through, so the result has real reveals instead of a coplanar sliver."""
    ux, uy = -ny, nx
    pts = []
    for su, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append((cx + ux * su * w / 2 + nx * sn * depth / 2,
                    cy + uy * su * w / 2 + ny * sn * depth / 2))
    return prism_mesh(pts, z, z + h, mat='reveal')


if __name__ == '__main__':
    spec = os.path.abspath(arg('--spec', 'place/harbour-town/spec'))
    geom, parts, log = build(spec)
    tris = sum(len(f) - 2 for _, _, F in parts for f in F)
    print('[solid] ' + '  '.join(f'{k}={v}' for k, v in log.items()
                                 if not k.endswith('failures')))
    for k in ('carve_failures', 'pierce_failures'):
        if log.get(k):
            print(f'[solid] {k}: {len(log[k])}  first: {log[k][0]}')
    print(f'[solid] {len(parts)} parts, {tris} triangles')
