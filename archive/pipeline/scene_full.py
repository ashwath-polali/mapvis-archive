"""
scene_full.py - every layer at once, on a COMPOSED map. The first honest attempt.

Everything before this built one layer and hoped. The measured apportionment from
docs/THE-PICTURE.md is:

    plan + hero structure   ~20%   modelled     <- compose.py + kit/
    edge & level profile    ~15%   modelled     <- ops_edges (automatic)
    facade grammar          ~10%   PAINTED      <- artist assets, not my extruder
    attachments             ~8%    small parts  <- NEVER BUILT until now
    inhabitation            ~10%   props        <- NEVER BUILT until now
    contact joints          ~10%   scatter      <- NEVER BUILT on a real map
    light                   ~20%   ---          <- cold key + placed warm points
    camera & atmosphere     ~7%    ---

Four of those eight layers had never been built on any map by any method, and
together they are 43% of the read. The 6.4 GB CC0 library has been sitting unused
the whole time: 105 KayKit forest models, 345 more vegetation, and the Kenney
fantasy-town kit which is nothing but the attachment and inhabitation vocabulary -
fountains, hedges, lanterns, carts, banners, chimneys, balconies, pillars.

So: my kit for the STRUCTURE it is genuinely good at (retaining walls, flights,
quays, arches), artist models for the MASSES my extruder makes badly, artist props
on sockets the geometry computes, and vegetation in every contact joint. Nothing
is placed by taste - every socket is a measured condition.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P scene_full.py -- --spec place/harbour-town/spec
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
A = os.path.join(HERE, 'assets')
CHAR = 1.7
STOREY = 3.2

LIB = {
    'house':   f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/house.gltf.glb',
    'market':  f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/market.gltf.glb',
    'mill':    f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/mill.gltf.glb',
    'watermill': f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/watermill.gltf.glb',
    'barracks': f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/barracks.gltf.glb',
    'tower':   f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/watchtower.gltf.glb',
    'castle':  f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/castle.gltf.glb',
    'well':    f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/well.gltf.glb',
    'bridge':  f'{A}/kits/kaykit-medieval-builder/Models/objects/gltf/bridge.gltf.glb',
}
TOWN = f'{A}/kenney/fantasy-town-kit/Models/GLB format'
PROPS = {k: f'{TOWN}/{k}.glb' for k in
         ('fountain-round', 'lantern', 'cart', 'cart-high', 'hedge', 'hedge-large',
          'fence', 'fence-curved', 'banner-red', 'banner-green', 'chimney',
          'pillar-stone', 'planks', 'overhang')}
FOREST = f'{A}/kits/kaykit-forest/KayKit_Forest_Nature_Pack_1.0_FREE/Assets/gltf'

_TPL = {}


def template(path, name):
    """Import once, measure, park it out of frame, then instance it. Importing per
    placement would multiply the mesh data by the placement count."""
    if name in _TPL:
        return _TPL[name]
    if not os.path.exists(path):
        return None
    before = set(bpy.context.scene.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception:
        return None
    new = [o for o in bpy.context.scene.objects if o not in before and o.type == 'MESH']
    if not new:
        return None
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for c in ob.bound_box:
        w = ob.matrix_world @ Vector(c)
        lo = Vector(min(lo[i], w[i]) for i in range(3))
        hi = Vector(max(hi[i], w[i]) for i in range(3))
    ob.hide_render = True
    ob.location = Vector((0, 0, -9999))
    bpy.ops.object.select_all(action='DESELECT')
    _TPL[name] = (ob, lo, hi)
    return _TPL[name]


def inst(tpl, x, y, z, rot=0.0, target_w=None, scale=None):
    if tpl is None:
        return None
    ob, lo, hi = tpl
    s = scale if scale else (target_w / (max(hi.x - lo.x, hi.y - lo.y) or 1.0)
                             if target_w else 1.0)
    d = ob.copy()
    d.data = ob.data
    d.hide_render = False
    bpy.context.collection.objects.link(d)
    d.scale = (s, s, s)
    d.rotation_euler = (0, 0, rot)
    d.location = Vector((x, y, z - lo.z * s))
    return d


def forest_models():
    out = []
    if not os.path.isdir(FOREST):
        return out
    for f in sorted(os.listdir(FOREST)):
        if f.endswith('.gltf') and ('Bush' in f or 'Grass' in f or 'Tree' in f):
            out.append((os.path.join(FOREST, f), f[:-5]))
    return out


# ------------------------------------------------------------------ structure

def structure(spec):
    """The ground, terraces, retaining walls, flights, quays and guards, from my
    own kit - the one thing it is genuinely good at."""
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
            print(f'[full] edges: {st["edges"]} found, '
                  f'{sum(v["runs"] for v in st["per_profile"].values())} profile runs')
        except Exception as e:
            print(f'[full] edges skipped: {type(e).__name__}')
    for mat, v, f in parts:
        B.emit(mat, v, f)
    objs = B.flush()
    return geom, objs


# ------------------------------------------------------------------ the layers

def masses(geom, step):
    """Artist buildings on the COMPOSED blocks. The extruder makes these badly and
    an artist already made them well; the machine's job is which and where, which
    is a measured question, not a taste one."""
    blocks = sorted(geom.get('blocks', []), key=lambda b: -poly_area(b['pts']))
    if not blocks:
        return 0
    roles = ['house', 'house', 'market', 'house', 'mill', 'house', 'barracks',
             'house', 'watermill', 'house', 'tower']
    n = 0
    for i, blk in enumerate(blocks):
        poly = [tuple(p) for p in blk['pts']]
        a = poly_area(poly)
        if a < 30:
            continue
        ang, w, d, (cx, cy) = obb(poly)
        z = blk['level'] * step
        # the biggest block on the highest level takes the landmark
        name = 'castle' if i == 0 else roles[i % len(roles)]
        t = template(LIB[name], name)
        if t is None:
            continue
        inst(t, cx, cy, z, ang, target_w=max(5.0, min(max(w, d), 24.0)))
        n += 1
    return n


def inhabitation(geom, spec, step):
    """The temporary layer that belongs to no footprint - 10% of the read and 0%
    built before now. Sockets: the widest walkable point takes the fountain, the
    route takes lanterns, block frontages take carts and banners."""
    route = json.load(open(os.path.join(spec, 'route.json')))
    ox, oy = route.get('origin', [0, 0])
    pts = [(p[0] - ox, p[1] - oy, p[2]) for p in route['polyline']]
    n = 0

    # ONE landmark object in open ground (LM-4: exactly one, never more)
    st = route.get('stations', [])
    if st:
        widest = max(st, key=lambda s: s.get('room_m', 0))
        t = template(PROPS['fountain-round'], 'fountain')
        if t and inst(t, widest['x'] - ox, widest['y'] - oy,
                      widest.get('z', 0), 0, target_w=3.4):
            n += 1

    # lanterns down the route: light marks the way, and the post is also a
    # known-size scale referent (R3)
    lt = template(PROPS['lantern'], 'lantern')
    for i, p in enumerate(pts):
        if lt and i % 2 == 0:
            side = 1.9 if i % 4 == 0 else -1.9
            inst(lt, p[0] + side, p[1], p[2], 0, target_w=0.5)
            n += 1

    # carts, hedges and banners against block frontages
    for i, blk in enumerate(geom.get('blocks', [])):
        poly = [tuple(p) for p in blk['pts']]
        if poly_area(poly) < 40:
            continue
        a, b = longest_edge(poly)
        ux, uy, L = seg(a, b)
        if L < 5:
            continue
        nx, ny = uy, -ux
        z = blk['level'] * step
        for frac, key, w in ((0.28, 'cart', 2.0), (0.62, 'hedge', 1.6),
                             (0.85, 'banner-red', 1.2)):
            t = template(PROPS[key], key)
            if not t:
                continue
            px = a[0] + ux * L * frac + nx * 1.3
            py = a[1] + uy * L * frac + ny * 1.3
            inst(t, px, py, z, math.atan2(uy, ux), target_w=w)
            n += 1
    return n


def contact(geom, spec, step):
    """Nothing meets anything without something growing in the joint. Highest
    value per unit of effort in the whole stack, and the reason extrusion always
    reads as a model: it meets ground on a razor seam."""
    models = forest_models()
    if not models:
        return 0
    tpls = [template(p, nm) for p, nm in models[:22]]
    tpls = [t for t in tpls if t]
    if not tpls:
        return 0
    n = 0
    # along every terrace lip and every quay run, at a pitch, with gaps
    runs = []
    for r in geom.get('parapets', []):
        runs.append((r, step * level_of(r, geom)))
    for r in geom.get('quays', []):
        runs.append((r, 0.35))
    for run, z in runs:
        for i in range(len(run) - 1):
            a, b = run[i], run[i + 1]
            ux, uy, L = seg(a, b)
            k = 0
            while k * 1.4 < L:
                t = k * 1.4
                h = (int(a[0] * 7 + a[1] * 13 + k * 29)) % 11
                if h > 3:
                    tpl = tpls[h % len(tpls)]
                    off = 0.55 + 0.25 * ((h % 3) / 3.0)
                    inst(tpl, a[0] + ux * t + uy * off, a[1] + uy * t - ux * off, z,
                         (h % 8) * 0.78, target_w=0.5 + 0.35 * (h % 4) / 4.0)
                    n += 1
                k += 1
    return n


def vegetation(geom, grids, step, span):
    """Trees on the non-walkable, non-built ground. 450 CC0 vegetation models have
    been on disk unused for the whole project, and foliage is most of what fills
    an Octopath frame's dead space."""
    models = [m for m in forest_models() if 'Tree' in m[1] or 'Bush_4' in m[1]]
    if not models:
        models = forest_models()
    tpls = [template(p, nm) for p, nm in models[:14]]
    tpls = [t for t in tpls if t]
    if not tpls:
        return 0
    lvl, walk, built = grids['lvl'], grids['walk'], grids['built']
    free = (lvl >= 0) & ~walk & ~built
    ys, xs = np.nonzero(free)
    if not len(xs):
        return 0
    res = geom['res']
    n = 0
    stride = max(1, len(xs) // int(arg('--trees', 160)))
    for i in range(0, len(xs), stride):
        x, y = float(xs[i]) * res, float(ys[i]) * res
        h = (int(x * 11 + y * 17)) % 13
        if h < 4:
            continue
        tpl = tpls[h % len(tpls)]
        inst(tpl, x, y, float(lvl[ys[i], xs[i]]) * step, (h % 8) * 0.78,
             target_w=1.6 + 1.9 * (h % 5) / 5.0)
        n += 1
    return n


# ------------------------------------------------------------------ helpers

def poly_area(p):
    s = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def seg(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return (dx / L, dy / L, L) if L > 1e-9 else (1.0, 0.0, 0.0)


def longest_edge(poly):
    best, out = -1, (poly[0], poly[1 % len(poly)])
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = math.dist(a, b)
        if d > best:
            best, out = d, (a, b)
    return out


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


def level_of(run, geom):
    px, py = run[len(run) // 2]
    best = 0
    for t in geom['terraces']:
        for loop in t['loops']:
            if point_in(px, py, loop):
                best = max(best, t['level'])
    return best


def point_in(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                inside = not inside
    return inside


# ------------------------------------------------------------------ light/cam

def warm(x, y, z, power=200.0, size=0.4):
    d = bpy.data.lights.new('pt', 'POINT')
    d.energy = power
    d.color = (1.0, 0.60, 0.27)
    d.shadow_soft_size = size
    o = bpy.data.objects.new('pt', d)
    bpy.context.collection.objects.link(o)
    o.location = Vector((x, y, z))


def lights_camera(spec, geom):
    route = json.load(open(os.path.join(spec, 'route.json')))
    ox, oy = route.get('origin', [0, 0])
    pts = [(p[0] - ox, p[1] - oy, p[2]) for p in route['polyline']]

    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.055, 0.075, 0.115, 1)
    key = bpy.data.lights.new('key', 'SUN')
    key.energy = float(arg('--key', 3.1))
    key.color = (1.0, 0.86, 0.66)
    key.angle = math.radians(3)
    ko = bpy.data.objects.new('key', key)
    bpy.context.collection.objects.link(ko)
    ko.rotation_euler = (math.radians(56), 0, math.radians(-46))
    fill = bpy.data.lights.new('fill', 'SUN')
    fill.energy = 0.5
    fill.color = (0.55, 0.70, 1.0)
    fo = bpy.data.objects.new('fill', fill)
    bpy.context.collection.objects.link(fo)
    fo.rotation_euler = (math.radians(118), 0, math.radians(-150))

    thr = route.get('principal_threshold', len(pts) // 2)
    for i, p in enumerate(pts):
        if i == thr:
            warm(p[0], p[1], p[2] + 3.2, 700, 0.6)
        elif i % 2 == 0:
            warm(p[0], p[1], p[2] + 2.6, 180)

    span = geom['span_m']
    cd = bpy.data.cameras.new('cam')
    cd.lens = float(arg('--lens', 50))
    cd.clip_start, cd.clip_end = 0.4, 2000
    cd.dof.use_dof = True
    cam = bpy.data.objects.new('cam', cd)
    bpy.context.collection.objects.link(cam)
    pitch = math.radians(float(arg('--pitch', 24)))

    if flag('--place'):
        # THE PLACE CAMERA. Octopath is never seen from above the model - it is seen
        # from a low telephoto standing on the route, and a whole map is only ever
        # glimpsed a slice at a time. An overview is not how this is judged.
        i = int(arg('--station', max(1, thr)))
        i = max(1, min(i, len(pts) - 2))
        a = Vector(pts[i])
        look = Vector(pts[i + 1]) - a
        look.z = 0
        if look.length < 1e-6:
            look = Vector((0, 1, 0))
        look.normalize()
        back = float(arg('--dist', 22))
        eye = a - look * back + Vector((0, 0, 1.6 + back * math.sin(pitch) * 0.8))
        tgt = a + look * 12.0 + Vector((0, 0, 2.2))
        cam.location = eye
        d = tgt - eye
        cam.rotation_euler = (math.radians(90) - math.atan2(-d.z, math.hypot(d.x, d.y)),
                              0, math.atan2(d.y, d.x) - math.pi / 2)
        cd.dof.focus_distance = max(6.0, d.length)
        cd.dof.aperture_fstop = float(arg('--fstop', 2.4))
        print(f'[full] place camera at station {i}, standoff {back:.0f} m')
    else:
        dist = float(arg('--dist', span * 1.15))
        tgt = Vector((span * 0.5, span * 0.5, 6.0))
        cam.location = tgt + Vector((0, -dist * math.cos(pitch), dist * math.sin(pitch)))
        cam.rotation_euler = (math.radians(90) - pitch, 0, 0)
        cd.dof.focus_distance = dist
        cd.dof.aperture_fstop = float(arg('--fstop', 6.0))
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
    geom, objs = structure(SPEC)
    grids = np.load(os.path.join(SPEC, 'grids.npz'))
    step = geom['level_step_m']
    nm = masses(geom, step)
    ni = inhabitation(geom, SPEC, step)
    nc = contact(geom, SPEC, step)
    nv = vegetation(geom, grids, step, geom['span_m'])
    print(f'[full] masses {nm}  inhabitation {ni}  contact {nc}  vegetation {nv}')
    lights_camera(SPEC, geom)
    tris = 0
    for ob in bpy.context.scene.objects:
        if ob.type == 'MESH' and not ob.hide_render:
            ob.data.calc_loop_triangles()
            tris += len(ob.data.loop_triangles)
    p = os.path.join(HERE, 'shots', f'full-{os.path.basename(os.path.dirname(SPEC))}.png')
    render(p)
    print(f'[full] {tris} triangles -> {p}')
