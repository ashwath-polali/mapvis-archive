"""
render_map.py - render a composed map with the full stack, at the place camera.

Everything the theory says carries the read, applied to a COMPOSED map rather
than a hand-built scene:

  ops_edges    a profile on every horizontal top edge, found automatically. The
               flat cap is the largest single reason terraces read as a contour
               diagram, and it is the cheapest thing to fix.
  light        one cold wide key plus a handful of warm points on the route, most
               of the frame allowed to go near-black. ~20% of the read and the
               largest single lever.
  camera       measured off 50 reference town frames: perspective, ~19 deg down,
               focus band peaking at y=47% of frame.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P render_map.py -- --spec place/harbour-town/spec
"""
import json
import math
import os
import sys

import bpy
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

# The palette is a VALUE ramp, not colour choices: stone reads mid, timber and
# roof read dark, water reads near-black. Value separation is what the reference
# frames have and what a uniform grey model does not.
MAT = {
    'water':   (0.014, 0.030, 0.044, 0.06),
    'rock':    (0.150, 0.145, 0.140, 0.95),
    'ashlar':  (0.290, 0.281, 0.264, 0.86),
    'quay_block': (0.255, 0.248, 0.236, 0.88),
    'flag':    (0.235, 0.229, 0.218, 0.90),
    'cobble':  (0.215, 0.209, 0.199, 0.92),
    'dirt':    (0.175, 0.152, 0.120, 0.95),
    'step':    (0.315, 0.303, 0.284, 0.88),
    'stone_course': (0.300, 0.290, 0.272, 0.86),
    'coping':  (0.335, 0.325, 0.305, 0.85),
    'plaster': (0.385, 0.362, 0.325, 0.92),
    'brick':   (0.165, 0.098, 0.075, 0.92),
    'plaster_timber': (0.360, 0.338, 0.300, 0.92),
    'timber':  (0.095, 0.068, 0.045, 0.90),
    'plank':   (0.105, 0.075, 0.050, 0.90),
    'tile':    (0.150, 0.082, 0.058, 0.92),
    'shingle': (0.130, 0.078, 0.058, 0.92),
    'moss':    (0.048, 0.066, 0.032, 0.98),
    'algae':   (0.040, 0.055, 0.036, 0.55),
    'reveal':  (0.070, 0.066, 0.062, 0.95),
}


def material(name):
    key = 'px_' + name
    if key in bpy.data.materials:
        return bpy.data.materials[key]
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    r, g, bl, rough = MAT.get(name, (0.26, 0.25, 0.24, 0.9))
    b.inputs['Base Color'].default_value = (r, g, bl, 1)
    b.inputs['Roughness'].default_value = rough
    if name == 'water' and 'Metallic' in b.inputs:
        b.inputs['Metallic'].default_value = 0.45
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = 0.10
    return m


def build(spec):
    if flag('--solid'):
        import assemble_solid as S
        geom, parts, log = S.build(spec)
        print('[render] subtractive: ' + '  '.join(
            f'{k}={v}' for k, v in log.items() if not k.endswith('failures')))
        return finish(geom, parts)
    import assemble_map as A
    import build_place as B
    geom = json.load(open(os.path.join(spec, 'geom.json')))
    step = geom['level_step_m']
    A.SPEC = spec
    A.PARTS.clear()
    A.ground(geom, step)
    A.rule_quays(geom, step)
    A.rule_guards(geom, step)
    A.rule_flights(geom, step)
    A.rule_masses(geom, step)
    A.rule_openings(geom, step)

    parts = list(A.PARTS)
    if not flag('--no-edges'):
        import ops_edges as OE
        try:
            extra, stats = OE.apply_to_parts(parts, verbose=False)
            parts += list(extra)
            print(f'[render] edge operator: {len(extra)} profile runs over '
                  f'{stats["edges"]} top edges, {stats["chains"]} chains, '
                  f'{sum(v["runs"] for v in stats["per_profile"].values())} runs: '
                  f'{ {k: v["runs"] for k, v in stats["per_profile"].items()} }')
        except Exception as e:
            print(f'[render] edge operator skipped: {type(e).__name__}: {str(e)[:110]}')

    return finish(geom, parts)


def finish(geom, parts):
    groups = {}
    for mat, v, f in parts:
        groups.setdefault(mat, []).append((v, f))
    objs, tris = [], 0
    for mat, ps in groups.items():
        V, F = [], []
        for v, f in ps:
            o = len(V)
            V += list(v)
            F += [tuple(i + o for i in q) for q in f]
        me = bpy.data.meshes.new(mat)
        me.from_pydata(V, [], F)
        me.validate(verbose=False)
        ob = bpy.data.objects.new(mat, me)
        bpy.context.collection.objects.link(ob)
        md = ob.modifiers.new('bev', 'BEVEL')
        md.width = 0.012
        md.segments = 2
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(35)
        ob.data.materials.append(material(mat))
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        objs.append(ob)
    return geom, objs, tris


def warm(x, y, z, power=140.0, size=0.4):
    d = bpy.data.lights.new('pt', 'POINT')
    d.energy = power
    d.color = (1.0, 0.60, 0.28)
    d.shadow_soft_size = size
    o = bpy.data.objects.new('pt', d)
    bpy.context.collection.objects.link(o)
    o.location = Vector((x, y, z))


def lights_and_camera(spec, geom):
    route = json.load(open(os.path.join(spec, 'route.json')))
    ox, oy = route.get('origin', [0, 0])
    pts = [(p[0] - ox, p[1] - oy, p[2]) for p in route['polyline']]
    step = geom['level_step_m']

    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.030, 0.046, 0.082, 1)
    key = bpy.data.lights.new('key', 'SUN')
    key.energy = 2.6
    key.color = (0.50, 0.63, 1.0)
    key.angle = math.radians(5)
    ko = bpy.data.objects.new('key', key)
    bpy.context.collection.objects.link(ko)
    ko.rotation_euler = (math.radians(63), 0, math.radians(-54))

    # warm points ON THE ROUTE, so light marks the way through. The hero sits at
    # the principal threshold, which is the station the composer already chose.
    thr = route.get('principal_threshold', len(pts) // 2)
    for i, p in enumerate(pts):
        if i == thr:
            warm(p[0], p[1], p[2] + 3.0, 900, 0.7)
        elif i % 2 == 0:
            warm(p[0], p[1], p[2] + 2.4, 260)

    # STAND THE CAMERA ON THE ROUTE. The route is walkable by construction, so a
    # station is guaranteed to be open space - a stand-off computed from a target
    # put the lens inside a block, which is how the last render came back as a
    # dark wedge. Look FORWARD along the route at the threshold.
    # Look ALONG the street, not across it. Aiming from a station N steps back at
    # the threshold cuts a chord across the intervening blocks and puts the lens
    # against a wall; the street direction is the LOCAL tangent.
    tgt_i = min(max(thr, 1), len(pts) - 2)
    a = Vector(pts[tgt_i])
    b = Vector(pts[tgt_i + 1])
    look = (b - a)
    look.z = 0
    if look.length < 1e-6:
        look = Vector((0, 1, 0))
    look.normalize()
    # The camera must stand INSIDE the carved street. A long standoff walks the
    # lens back out of the void and into the solid, which is how the last frame
    # came back black. Stay on the station, back off by a couple of metres only,
    # and let a wide lens do the work a long standoff was doing.
    dist = float(arg('--dist', 5))
    eye = a - look * dist + Vector((0, 0, 1.62))
    tgt = a + look * 14.0 + Vector((0, 0, 2.0))

    cd = bpy.data.cameras.new('cam')
    cd.lens = float(arg('--lens', 42))
    cd.clip_start, cd.clip_end = 0.3, 900
    cd.dof.use_dof = True
    cd.dof.focus_distance = 14.0
    cd.dof.aperture_fstop = float(arg('--fstop', 2.2))
    cam = bpy.data.objects.new('cam', cd)
    bpy.context.collection.objects.link(cam)
    # lift and pitch down onto the route, which is the measured place camera
    pitch = math.radians(float(arg('--pitch', 17)))
    cam.location = eye
    d = (tgt - cam.location)
    cam.rotation_euler = (math.radians(90) - math.atan2(-d.z, math.hypot(d.x, d.y)), 0,
                          math.atan2(d.y, d.x) - math.pi / 2)
    print(f'[render] camera in street at station {tgt_i}, standoff {dist:.1f} m, '
          f'eye ({cam.location.x:.1f}, {cam.location.y:.1f}, {cam.location.z:.1f})')
    bpy.context.scene.camera = cam


def render(path):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 96
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
    geom, objs, tris = build(SPEC)
    lights_and_camera(SPEC, geom)
    tag = os.path.basename(os.path.dirname(SPEC))
    p = os.path.join(HERE, 'shots', f'map-{tag}.png')
    render(p)
    print(f'[render] {len(objs)} objects, {tris} triangles -> {p}')
