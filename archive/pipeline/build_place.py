"""
build_place.py - the derived spec -> real 3D geometry, in Blender.

Consumes only `geom.json` (traced polygons) and `vectors.json` (surveyed
footprints). It never sees a raster, so there is no per-cell geometry anywhere
and therefore no "melted" crumb-staircase terrain - that defect is structurally
impossible here rather than merely avoided.

Every object it makes exists because the measured ground forced it:

    terrace cap   a level's region, flat, at its integer height       EL-1
    retaining     the skirt of that cap down to the level below       layer 2
    parapet       a walkable edge that has a fall beside it           ED-2
    stair         a street crossing a level boundary                  EL-5
    quay          land meeting sea
    mass          a real surveyed footprint at its surveyed storeys   MA-5/6

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P build_place.py -- --spec place/villefranche/spec
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


SPEC = os.path.abspath(arg('--spec', 'place/villefranche/spec'))
OUT = arg('--out', 'shots')
TEXTURED = '--grey' not in ARGV
HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, 'tex')
os.makedirs(os.path.join(HERE, OUT), exist_ok=True)

STOREY = 3.2          # metres. checked against CHAR 1.7
SEA_Z = -1.6
TEXEL = {'cobble': 2.0, 'dirt': 3.0, 'stone_course': 2.0, 'quay_block': 2.4,
         'brick': 1.6, 'shingle': 1.6, 'plaster_timber': 3.0, 'plank': 1.4}

BUCKETS = {}          # material name -> list of (verts, faces), merged at the end


def emit(mat, verts, faces):
    BUCKETS.setdefault(mat, []).append((verts, faces))


# ------------------------------------------------------------------ primitives

def prism(poly, z0, z1, cap_top=True, cap_bottom=False):
    """A closed polygon lofted between two heights. Clean vertical faces."""
    n = len(poly)
    v = [(p[0], p[1], z0) for p in poly] + [(p[0], p[1], z1) for p in poly]
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if cap_top:
        f.append(tuple(range(n, 2 * n)))
    if cap_bottom:
        f.append(tuple(range(n - 1, -1, -1)))
    return v, f


def ribbon(line, z0, z1, half_w):
    """An open polyline given thickness and height - walls, parapets, copings."""
    if len(line) < 2:
        return None
    left, right = [], []
    for i, p in enumerate(line):
        a = line[max(0, i - 1)]
        b = line[min(len(line) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / m * half_w, dx / m * half_w
        left.append((p[0] + nx, p[1] + ny))
        right.append((p[0] - nx, p[1] - ny))
    poly = left + right[::-1]
    return prism(poly, z0, z1, cap_top=True)


def obb(poly):
    """Minimum-area oriented box. Real footprints are near-rectangular, so this
    gives the roof a truthful ridge direction without anyone choosing one."""
    best = None
    for deg in range(0, 90, 2):
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        xs = [p[0] * c + p[1] * s for p in poly]
        ys = [-p[0] * s + p[1] * c for p in poly]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if best is None or w * h < best[0]:
            best = (w * h, a, min(xs), max(xs), min(ys), max(ys))
    _, a, x0, x1, y0, y1 = best
    c, s = math.cos(a), math.sin(a)

    def back(u, v):
        return (u * c - v * s, u * s + v * c)
    return a, (x0, x1, y0, y1), back


def gable(poly, z_base, h_wall, pitch=0.42, overhang=0.5):
    """Box + prism roof, which is what an Octopath building is."""
    ang, (x0, x1, y0, y1), back = obb(poly)
    x0 -= overhang; x1 += overhang; y0 -= overhang; y1 += overhang
    long_x = (x1 - x0) >= (y1 - y0)
    ridge_h = (min(x1 - x0, y1 - y0) * 0.5) * pitch * 2
    ridge_h = max(1.2, min(ridge_h, 4.2))
    zt = z_base + h_wall
    if long_x:
        ym = (y0 + y1) / 2
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        ridge = [(x0, ym), (x1, ym)]
    else:
        xm = (x0 + x1) / 2
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        ridge = [(xm, y0), (xm, y1)]
    c = [back(u, v) for u, v in corners]
    r = [back(u, v) for u, v in ridge]
    v = [(p[0], p[1], zt) for p in c] + [(p[0], p[1], zt + ridge_h) for p in r]
    if long_x:
        f = [(0, 3, 2, 1), (0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4)]
    else:
        f = [(0, 3, 2, 1), (1, 2, 5, 4), (3, 0, 4, 5), (0, 1, 4), (2, 3, 5)]
    return v, f


# ------------------------------------------------------------------ the build

def build(geom, vec):
    step = geom['level_step_m']
    span = geom['span_m']
    k = geom['levels']

    # --- sea. one plane, generous, so the map sits IN water not on a table
    pad = span * 1.5
    emit('quay_block', *prism([(-pad, -pad), (span + pad, -pad),
                               (span + pad, span + pad), (-pad, span + pad)],
                              SEA_Z - 6, SEA_Z))

    # --- terraces: cap + the retaining wall that must hold it up
    for t in geom['terraces']:
        L, z = t['level'], t['z']
        below = (L - 1) * step if L > 0 else SEA_Z
        for loop in t['loops']:
            if len(loop) < 3:
                continue
            emit('dirt', *prism(loop, below, z, cap_top=True))
            # a plinth proud of the wall face, and an oversailing coping.
            # both are layer-2 vocabulary and both are forced, not chosen.
            if z - below > 1.2:
                emit('quay_block', *prism(inflate(loop, 0.35), below, below + 0.55))
                emit('stone_course', *prism(inflate(loop, 0.28), z - 0.30, z + 0.06))

    # --- streets: their own surface, proud of the terrace, with a kerb face
    for wgrp in geom.get('ways', []):
        z = wgrp['level'] * step
        for loop in wgrp['loops']:
            if len(loop) >= 3:
                emit('cobble', *prism(loop, z + 0.02, z + 0.16, cap_top=True))

    # --- parapets: ED-2, every internal drop edge carries a guard
    for run in geom['parapets']:
        z = sample_level_z(run, geom, step)
        r = ribbon(run, z, z + 0.95, 0.30)
        if r:
            emit('stone_course', *r)

    # --- quays: land meeting sea
    for run in geom['quays']:
        r = ribbon(run, SEA_Z, 0.35, 0.9)
        if r:
            emit('quay_block', *r)

    # --- stairs: EL-5, forced wherever a street crosses a level boundary.
    # Oriented up the slope, sized by the street it carries.
    made = 0
    for s in geom['stairs']:
        if s['rise_m'] < 0.8:
            continue
        v, f = stair_mesh(s['x'], s['y'], s['w'], s['run'],
                          s['from'] * step, s['to'] * step, s['treads'],
                          s['ux'], s['uy'])
        emit('stone_course', v, f)
        # cheek walls: a flight without them is a ramp with lines on it
        for side in (-1, 1):
            cx = s['x'] - s['uy'] * side * (s['w'] / 2 + 0.25)
            cy = s['y'] + s['ux'] * side * (s['w'] / 2 + 0.25)
            cv, cf = stair_mesh(cx, cy, 0.5, s['run'], s['from'] * step,
                                s['to'] * step + 0.55, 2, s['ux'], s['uy'])
            emit('quay_block', cv, cf)
        made += 1

    # --- masses. MA-5: no freestanding mass. A block is ONE continuous built
    # wall closing the street, subdivided into bays that each get their own
    # gable and their own height - which is what a real terrace row is, and what
    # Octopath's street walls are. Heights come from the surveyed storey counts
    # of the OSM buildings that actually stand inside each block.
    nb, nbay = 0, 0
    for i, blk in enumerate([] if '--no-blocks' in ARGV else geom.get('blocks', [])):
        poly = dedupe(blk['pts'])
        if len(poly) < 3 or abs(area(poly)) < 40:
            continue
        zb = blk['level'] * step
        st = storeys_in(poly, vec['buildings'])
        h = (sum(st) / len(st)) * STOREY
        # ONE continuous mass per block. Slicing the block's bounding box into
        # bays produced rotated boxes that ignored the block's real shape and
        # each other - the "floating shards". A terrace row IS one mass; that is
        # what MA-5 means by a continuous street wall.
        emit('brick' if i % 3 else 'plaster_timber',
             *prism(poly, zb - 2.5, zb + h, cap_top=False))
        emit('stone_course', *prism(inflate(poly, 0.22), zb - 2.5, zb + 0.8))
        # eaves band then an inset cap: reads as a roof from the place camera
        # without needing a hip solve on an arbitrary polygon.
        emit('shingle', *prism(inflate(poly, 0.45), zb + h, zb + h + 0.45))
        emit('shingle', *prism(inflate(poly, -1.1), zb + h + 0.45, zb + h + 1.5))
        nbay += 1
        nb += 1

    print(f'[build] {k} terraces, {len(geom["parapets"])} parapets, '
          f'{made} stairs, {nb} blocks in {nbay} bays')


def storeys_in(poly, buildings):
    """The surveyed storey counts of the real buildings inside this block."""
    got = []
    for b in buildings:
        if not b['storeys']:
            continue
        cx = sum(p[0] for p in b['pts']) / len(b['pts'])
        cy = sum(p[1] for p in b['pts']) / len(b['pts'])
        if point_in(cx, cy, poly):
            got.append(b['storeys'])
    return got or [3]


def bays(poly, storey_list, seed, bay_m=14.0):
    """Slice a block across its long axis into bays. Each bay is a house-width
    of the terrace row, and takes a height from the surveyed distribution, so
    the roofline varies the way a real street does without anyone choosing it."""
    ang, (x0, x1, y0, y1), back = obb(poly)
    w, h = x1 - x0, y1 - y0
    along_x = w >= h
    L = w if along_x else h
    n = max(1, int(round(L / bay_m)))
    out = []
    for i in range(n):
        t0, t1 = i / n, (i + 1) / n
        if along_x:
            a, b = x0 + w * t0, x0 + w * t1
            corners = [(a, y0), (b, y0), (b, y1), (a, y1)]
        else:
            a, b = y0 + h * t0, y0 + h * t1
            corners = [(x0, a), (x1, a), (x1, b), (x0, b)]
        quad = [back(u, v) for u, v in corners]
        # clip: only keep a bay whose centre is actually inside the block, so an
        # L-shaped or curved block does not get filled into its bounding box
        cx = sum(p[0] for p in quad) / 4
        cy = sum(p[1] for p in quad) / 4
        if not point_in(cx, cy, poly):
            continue
        st = storey_list[(seed * 7 + i * 3) % len(storey_list)]
        out.append((quad, st * STOREY))
    return out


def dedupe(pts, tol=0.05):
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > tol:
            out.append(tuple(p))
    if len(out) > 1 and math.dist(out[0], out[-1]) < tol:
        out.pop()
    return out


def area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return s / 2


def inflate(poly, d):
    """Offset outward by d. Cheap centroid-radial offset - exact enough for a
    plinth, and it never self-intersects on convex-ish footprints."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    out = []
    for x, y in poly:
        dx, dy = x - cx, y - cy
        m = math.hypot(dx, dy) or 1.0
        out.append((x + dx / m * d, y + dy / m * d))
    return out


def sample_level_z(run, geom, step):
    """Height of the terrace a run sits on: the highest terrace containing it."""
    px, py = run[len(run) // 2]
    best = 0.0
    for t in geom['terraces']:
        for loop in t['loops']:
            if point_in(px, py, loop):
                best = max(best, t['z'])
    return best


def ground_z(poly, geom, step):
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    best = 0.0
    for t in geom['terraces']:
        for loop in t['loops']:
            if point_in(cx, cy, loop):
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


def stair_mesh(cx, cy, w, run_len, z0, z1, steps, ux=0.0, uy=1.0):
    """A flight climbing along (ux,uy). Each tread is a solid step, so the
    silhouette reads as a flight rather than as corduroy stripes on a ramp."""
    v, f = [], []
    px, py = -uy, ux                       # across the flight
    rise = (z1 - z0) / steps
    go = run_len / steps
    for i in range(steps):
        t0 = -run_len / 2 + go * i
        t1 = t0 + go
        zt = z0 + rise * (i + 1)
        quad = []
        for tt, ss in ((t0, -1), (t0, 1), (t1, 1), (t1, -1)):
            quad.append((cx + ux * tt + px * ss * w / 2,
                         cy + uy * tt + py * ss * w / 2))
        base = len(v)
        v += [(p[0], p[1], z0 - 0.5) for p in quad]
        v += [(p[0], p[1], zt) for p in quad]
        f += [tuple(base + i2 for i2 in q) for q in
              [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
               (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
    return v, f


# ------------------------------------------------------------------ blender

def flush():
    """One object per material. Fewer objects = a scene that actually renders."""
    made = []
    for mat, parts in BUCKETS.items():
        V, F = [], []
        for verts, faces in parts:
            o = len(V)
            V += list(verts)
            F += [tuple(i + o for i in face) for face in faces]
        me = bpy.data.meshes.new(mat)
        me.from_pydata(V, [], F)
        me.validate(verbose=False)
        ob = bpy.data.objects.new(mat, me)
        bpy.context.collection.objects.link(ob)
        uv_world(ob, TEXEL.get(mat, 2.0))
        ob.data.materials.append(material(mat))
        made.append(ob)
    return made


def uv_world(ob, texel):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    for fa in bm.faces:
        n = fa.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in fa.loops:
            co = l.vert.co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            l[uv].uv = (u / texel, v / texel)
    bm.to_mesh(me)
    bm.free()


_MATS = {}


def material(name):
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    if TEXTURED and os.path.exists(os.path.join(TEX, name + '.png')):
        img = m.node_tree.nodes.new('ShaderNodeTexImage')
        img.image = bpy.data.images.load(os.path.join(TEX, name + '.png'))
        img.interpolation = 'Closest'
        img.extension = 'REPEAT'
        m.node_tree.links.new(img.outputs['Color'], b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = (0.62, 0.61, 0.60, 1)
    b.inputs['Roughness'].default_value = 0.88
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = 0.08
    _MATS[name] = m
    return m


def setup(span, textured):
    cam_d = bpy.data.cameras.new('cam')
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    shot = arg('--shot', 'game')
    tx, ty = float(arg('--tx', span * 0.5)), float(arg('--ty', span * 0.5))

    if shot == 'plan':
        cam_d.type = 'ORTHO'
        cam_d.ortho_scale = span * 1.05
        cam_d.clip_start, cam_d.clip_end = 1.0, 8000
        cam.location = Vector((span * 0.5, span * 0.5, 900))
        cam.rotation_euler = (0, 0, 0)
    else:
        # The Octopath place camera: PERSPECTIVE, low downward pitch, telephoto,
        # standing off so facades read frontal. Measured off 50 town frames: the
        # focus band peaks at y=47% and spans ~50% of frame height.
        cam_d.lens = float(arg('--lens', 85))
        cam_d.clip_start, cam_d.clip_end = 1.0, 8000
        pitch = math.radians(float(arg('--pitch', 26)))
        dist = float(arg('--dist', 260))
        tgt = Vector((tx, ty, float(arg('--tz', 12))))
        cam.location = tgt + Vector((0, -dist * math.cos(pitch),
                                     dist * math.sin(pitch)))
        cam.rotation_euler = (math.radians(90) - pitch, 0, 0)
    bpy.context.scene.camera = cam

    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (
        (0.055, 0.075, 0.125, 1) if textured else (0.30, 0.31, 0.34, 1))
    sun_d = bpy.data.lights.new('sun', 'SUN')
    sun_d.energy = 5.0 if textured else 3.2
    sun_d.color = (1.0, 0.87, 0.68) if textured else (1, 1, 1)
    sun_d.angle = math.radians(2.0)
    sun = bpy.data.objects.new('sun', sun_d)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(54), 0, math.radians(24))
    fill_d = bpy.data.lights.new('fill', 'SUN')
    fill_d.energy = 0.7
    fill_d.color = (0.55, 0.68, 1.0)
    fill = bpy.data.objects.new('fill', fill_d)
    bpy.context.collection.objects.link(fill)
    fill.rotation_euler = (math.radians(118), 0, math.radians(-150))


def render(path):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 48
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    geom = json.load(open(os.path.join(SPEC, 'geom.json')))
    vec = json.load(open(os.path.join(SPEC, 'vectors.json')))
    build(geom, vec)
    objs = flush()
    tris = 0
    for o in objs:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    setup(geom['span_m'], TEXTURED)
    tag = ('tex' if TEXTURED else 'grey') + '-' + arg('--shot', 'game')
    p = os.path.join(HERE, OUT, f'place-{tag}.png')
    render(p)
    print(f'[build] {len(objs)} objects, {tris} triangles -> {p}')
