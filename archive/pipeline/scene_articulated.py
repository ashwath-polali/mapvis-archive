"""
scene_articulated.py - parametric architecture at correct proportion, articulated.

WHY THIS EXISTS. Two mass sources have now been tried on a composed map and both
are eliminated by evidence:

  extruded footprints   correct proportion, zero articulation -> reads as a
                        topographic model. Rejected repeatedly.
  CC0 artist kits       KayKit / Kenney. Instant density, but the packs are
                        chunky exaggerated low-poly cartoon and the bar is
                        realistically-proportioned architecture carrying dense
                        painted detail. No composition or lighting turns a KayKit
                        lantern into an Octopath lantern. Rejected on sight.

What is left is the third source: parametric architecture built at REAL
proportion with REAL articulation. facade.py already does it - swept profiles,
arrays, booleans and a bevel on every arris, 15,284 faces for a 4-bay 3-floor
wall with plinth, string courses, dentilled cornice, moulded architraves,
projecting sills, hooded heads on brackets, cut openings, mullions and transoms.

It was dismissed earlier on the grounds that poly count is only ~3% of the look.
That was the wrong reading of a correct measurement: the poly count does not
matter, but PROPORTION and ARTICULATION do, and facade.py is the only thing here
that has either. Its openings are cut with a boolean, so they are holes rather
than the plaques the extruder was sticking on walls.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P scene_articulated.py -- --spec place/harbour-town/spec --place
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'kit'))

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


def flag(n):
    return n in ARGV


SPEC = os.path.abspath(arg('--spec', 'place/harbour-town/spec'))
CHAR = 1.7
STOREY = 3.4                    # facade.py's own floor height
BAY_W = 2.6


def poly_area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def obb(poly):
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
    c, s = math.cos(a), math.sin(a)
    return (a, x1 - x0, y1 - y0,
            ((x0 + x1) / 2 * c - (y0 + y1) / 2 * s, (x0 + x1) / 2 * s + (y0 + y1) / 2 * c))


def articulated_masses(geom, step, limit):
    """One articulated facade per block, bays and floors from the block's own
    dimensions. facade.py builds it in place at the origin, so each is baked to a
    template and instanced - building 30 of them live would take minutes."""
    import facade as F
    blocks = sorted(geom.get('blocks', []), key=lambda b: -poly_area(b['pts']))
    made, cache = 0, {}
    for blk in blocks[:limit]:
        poly = [tuple(p) for p in blk['pts']]
        if poly_area(poly) < 34:
            continue
        ang, w, d, (cx, cy) = obb(poly)
        long_side = max(w, d)
        if w < d:
            ang += math.pi / 2
        bays = max(2, min(int(round(long_side / BAY_W)), 9))
        floors = 4 if poly_area(poly) > 150 else 3
        key = (bays, floors)
        if key not in cache:
            before = set(bpy.context.scene.objects)
            F.facade(bays=bays, floors=floors, bay_w=BAY_W, floor_h=STOREY)
            new = [o for o in bpy.context.scene.objects
                   if o not in before and o.type == 'MESH']
            if not new:
                continue
            for o in new:
                o.select_set(True)
            bpy.context.view_layer.objects.active = new[0]
            if len(new) > 1:
                bpy.ops.object.join()
            tpl = bpy.context.view_layer.objects.active
            lo = Vector((1e9, 1e9, 1e9))
            for c in tpl.bound_box:
                p = tpl.matrix_world @ Vector(c)
                lo = Vector(min(lo[i], p[i]) for i in range(3))
            tpl.hide_render = True
            tpl.location = Vector((0, 0, -9999))
            bpy.ops.object.select_all(action='DESELECT')
            cache[key] = (tpl, lo)
        tpl, lo = cache[key]
        dup = tpl.copy()
        dup.data = tpl.data
        dup.hide_render = False
        bpy.context.collection.objects.link(dup)
        dup.rotation_euler = (0, 0, ang)
        dup.location = Vector((cx, cy, blk['level'] * step - lo.z))
        made += 1
    return made, len(cache)


def structure(spec):
    import assemble_map as AM
    import build_place as B
    geom = json.load(open(os.path.join(spec, 'geom.json')))
    step = geom['level_step_m']
    AM.SPEC = spec
    AM.PARTS.clear()
    AM.ground(geom, step)
    AM.rule_quays(geom, step)
    AM.rule_guards(geom, step)
    AM.rule_flights(geom, step)
    parts = list(AM.PARTS)
    if not flag('--no-edges'):
        import ops_edges as OE
        try:
            extra, st = OE.apply_to_parts(parts, verbose=False)
            parts += list(extra)
            print(f'[art] edges {st["edges"]} found, '
                  f'{sum(v["runs"] for v in st["per_profile"].values())} runs')
        except Exception as e:
            print(f'[art] edges skipped: {type(e).__name__}')
    for mat, v, f in parts:
        B.emit(mat, v, f)
    B.flush()
    return geom


def warm(x, y, z, power=200.0, size=0.4):
    d = bpy.data.lights.new('pt', 'POINT')
    d.energy = power
    d.color = (1.0, 0.62, 0.30)
    d.shadow_soft_size = size
    o = bpy.data.objects.new('pt', d)
    bpy.context.collection.objects.link(o)
    o.location = Vector((x, y, z))


def lights_camera(spec, geom):
    route = json.load(open(os.path.join(spec, 'route.json')))
    ox, oy = route.get('origin', [0, 0])
    pts = [(p[0] - ox, p[1] - oy, p[2]) for p in route['polyline']]
    thr = route.get('principal_threshold', len(pts) // 2)

    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.045, 0.062, 0.098, 1)
    key = bpy.data.lights.new('key', 'SUN')
    key.energy = float(arg('--key', 3.4))
    key.color = (1.0, 0.85, 0.63)
    key.angle = math.radians(2.5)
    ko = bpy.data.objects.new('key', key)
    bpy.context.collection.objects.link(ko)
    ko.rotation_euler = (math.radians(58), 0, math.radians(-44))
    fl = bpy.data.lights.new('fill', 'SUN')
    fl.energy = 0.45
    fl.color = (0.52, 0.68, 1.0)
    fo = bpy.data.objects.new('fill', fl)
    bpy.context.collection.objects.link(fo)
    fo.rotation_euler = (math.radians(120), 0, math.radians(-150))

    for i, p in enumerate(pts):
        if i == thr:
            warm(p[0], p[1], p[2] + 3.4, 800, 0.6)
        elif i % 2 == 0:
            warm(p[0], p[1], p[2] + 2.6, 170)

    span = geom['span_m']
    cd = bpy.data.cameras.new('cam')
    cd.lens = float(arg('--lens', 55))
    cd.clip_start, cd.clip_end = 0.4, 2500
    cd.dof.use_dof = True
    cam = bpy.data.objects.new('cam', cd)
    bpy.context.collection.objects.link(cam)
    pitch = math.radians(float(arg('--pitch', 21)))
    if flag('--place'):
        i = max(1, min(int(arg('--station', max(1, thr))), len(pts) - 2))
        a = Vector(pts[i])
        look = Vector(pts[i + 1]) - a
        look.z = 0
        if look.length < 1e-6:
            look = Vector((0, 1, 0))
        look.normalize()
        back = float(arg('--dist', 26))
        eye = a - look * back + Vector((0, 0, 1.6 + back * math.sin(pitch)))
        tgt = a + look * 14.0 + Vector((0, 0, 3.0))
        cam.location = eye
        dv = tgt - eye
        cam.rotation_euler = (math.radians(90) - math.atan2(-dv.z, math.hypot(dv.x, dv.y)),
                              0, math.atan2(dv.y, dv.x) - math.pi / 2)
        cd.dof.focus_distance = max(6.0, dv.length)
        cd.dof.aperture_fstop = float(arg('--fstop', 2.8))
    else:
        dist = float(arg('--dist', span * 1.1))
        tgt = Vector((span * 0.5, span * 0.5, 8.0))
        cam.location = tgt + Vector((0, -dist * math.cos(pitch), dist * math.sin(pitch)))
        cam.rotation_euler = (math.radians(90) - pitch, 0, 0)
        cd.dof.focus_distance = dist
        cd.dof.aperture_fstop = 8.0
    bpy.context.scene.camera = cam


def render(path):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 64
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
    geom = structure(SPEC)
    n, uniq = articulated_masses(geom, geom['level_step_m'],
                                 int(arg('--limit', 26)))
    print(f'[art] {n} articulated masses from {uniq} unique facade templates')
    lights_camera(SPEC, geom)
    tris = 0
    for ob in bpy.context.scene.objects:
        if ob.type == 'MESH' and not ob.hide_render:
            ob.data.calc_loop_triangles()
            tris += len(ob.data.loop_triangles)
    tag = os.path.basename(os.path.dirname(SPEC))
    p = os.path.join(HERE, 'shots', f'art-{tag}.png')
    render(p)
    print(f'[art] {tris} triangles -> {p}')
