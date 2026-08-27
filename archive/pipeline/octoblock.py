"""
octoblock.py - one street block at OCTOPATH'S ACTUAL GEOMETRIC COMPLEXITY.

The point of this file is to be embarrassingly simple. Verified at native pixels
against reference/octopath-bar/: an Octopath house is a BOX and a PRISM ROOF. The
half-timbering, the window, the shutters, the sill, the door, the arch, the string
course, the brick - all PAINTED. Nothing modelled. A house is under ~100 triangles.

So this scene is built the same way, and it renders in four stages so the question
"which layer carries the look" can be answered by looking rather than arguing:

    stage 1  grey, flat            - the naked-structure test
    stage 2  grey + light rig      - what light alone buys
    stage 3  + pixel textures      - what paint buys
    stage 4  + post stack          - the finished Octopath frame

Nothing here chooses anything. Every number is a dimension in metres, checked
against a 1.7 m person.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P octoblock.py -- --out shots/
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = 'shots'
for i, a in enumerate(ARGV):
    if a == '--out':
        OUT = ARGV[i + 1]
HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, 'tex')
os.makedirs(os.path.join(HERE, OUT), exist_ok=True)

CHAR = 1.7          # a person, metres. every dimension is checked against this.
LEVEL = 2.6         # one elevation step. EL-2 says ~1.0-1.5 CHAR; 2.6 m = 1.5 CHAR.


# ------------------------------------------------------------------ scene setup

def wipe():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def box(name, x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return mesh_from(name, v, f)


def gable_roof(name, x0, y0, x1, y1, z0, ridge_h, overhang=0.35):
    """A prism. This is the whole roof. Octopath's roofs are this."""
    x0 -= overhang; x1 += overhang
    y0 -= overhang; y1 += overhang
    xm = (x0 + x1) / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (xm, y0, z0 + ridge_h), (xm, y1, z0 + ridge_h)]
    f = [(0, 3, 2, 1), (0, 1, 4), (2, 3, 5), (1, 2, 5, 4), (3, 0, 4, 5)]
    return mesh_from(name, v, f)


def house(name, x0, y0, x1, y1, base_z, floors=2, ridge=2.0):
    """box + prism. two objects, ~14 faces. that is an Octopath building."""
    h = floors * 2.7
    body = box(name + '_body', x0, y0, base_z, x1, y1, base_z + h)
    roof = gable_roof(name + '_roof', x0, y0, x1, y1, base_z + h, ridge)
    return body, roof


def stair(name, x0, y0, x1, y1, z0, z1, steps):
    """A real flight. EL-3: 3-8 treads per flight, chunky nosing. The previous
    setpiece used 26 risers over 8 m and it read as corduroy."""
    verts, faces = [], []
    rise = (z1 - z0) / steps
    run = (y1 - y0) / steps
    for i in range(steps):
        zz0 = z0
        zz1 = z0 + rise * (i + 1)
        ya = y0 + run * i
        yb = y0 + run * (i + 1)
        base = len(verts)
        verts += [(x0, ya, zz0), (x1, ya, zz0), (x1, yb, zz0), (x0, yb, zz0),
                  (x0, ya, zz1), (x1, ya, zz1), (x1, yb, zz1), (x0, yb, zz1)]
        faces += [(base + i2 for i2 in q) for q in
                  [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                   (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
    return mesh_from(name, verts, [tuple(f) for f in faces])


def build_block():
    """A street: lower cobbled way, a retaining wall, an upper terrace with a
    party-wall row, a flight connecting them, a parapet on the drop edge.
    ED-2: every drop edge carries a guard. CI-1: one spine."""
    objs = {}

    # --- layer 1: ground, two discrete planes (never a slope)
    objs['ground_lower'] = ('cobble', box('ground_lower', -30, -17, -0.4, 30, 2.0, 0.0))
    objs['ground_upper'] = ('cobble', box('ground_upper', -22, 2.0, LEVEL - 0.4, 22, 18, LEVEL))

    # --- layer 2: what holds the ground up
    objs['retaining'] = ('quay_block', box('retaining', -22, 1.4, -0.4, 22, 2.0, LEVEL))
    # a plinth proud of the face - the one bit of relief that is worth modelling
    objs['plinth'] = ('quay_block', box('plinth', -22, 1.15, -0.4, 22, 1.4, 0.55))
    objs['coping'] = ('stone_course', box('coping', -22, 1.25, LEVEL, 22, 2.05, LEVEL + 0.22))

    # --- layer 3: circulation. one flight, 5 treads, hugging a corner (EL-6)
    objs['stair'] = ('stone_course', stair('stair', 2.0, -1.2, 6.4, 1.9, -0.4, LEVEL, 5))
    objs['cheek_l'] = ('quay_block', box('cheek_l', 1.6, -1.2, -0.4, 2.0, 1.9, LEVEL + 0.2))
    objs['cheek_r'] = ('quay_block', box('cheek_r', 6.4, -1.2, -0.4, 6.8, 1.9, LEVEL + 0.2))

    # --- layer 6: guards on the drop edge, broken by the stair opening
    for i, (a, b) in enumerate([(-22, 1.6), (6.8, 22)]):
        objs[f'parapet{i}'] = ('stone_course',
                               box(f'parapet{i}', a, 1.35, LEVEL + 0.22, b, 1.95, LEVEL + 1.05))

    # --- layer 4: masses. party-walled, never freestanding (MA-5)
    row = [(-19.5, -13.0, 2, 2.1), (-13.0, -7.6, 2, 2.4), (-7.6, -2.0, 2, 2.0),
           (1.2, 7.0, 2, 2.6), (7.0, 12.4, 2, 2.2), (12.4, 19.0, 2, 2.3)]
    for i, (x0, x1, fl, rg) in enumerate(row):
        body, roof = house(f'h{i}', x0, 3.4, x1, 11.0, LEVEL, fl, rg)
        objs[f'h{i}_body'] = ('plaster_timber' if i % 2 else 'brick', body)
        objs[f'h{i}_roof'] = ('shingle', roof)

    # foreground occluders at the frame edges only (LM-5). They frame the shot;
    # they must not block it, so the centre stays open.
    for i, (x0, x1) in enumerate([(-34, -19.5), (19.5, 34)]):
        body, roof = house(f'l{i}', x0, -16.5, x1, -9.0, -0.4, 3, 2.6)
        objs[f'l{i}_body'] = ('brick' if i % 2 else 'plaster_timber', body)
        objs[f'l{i}_roof'] = ('shingle', roof)

    # --- a THIRD plane further back. Octopath builds depth by stacking terraces
    # up-screen behind flat walls, not by rotating the camera.
    L2 = LEVEL * 2
    objs['ground_top'] = ('cobble', box('ground_top', -30, 12.5, L2 - 0.4, 30, 30, L2))
    objs['retain2'] = ('quay_block', box('retain2', -30, 11.9, LEVEL - 0.4, 30, 12.5, L2))
    objs['coping2'] = ('stone_course', box('coping2', -30, 11.75, L2, 30, 12.6, L2 + 0.22))
    for i, (a, b) in enumerate([(-30, -4.5), (7.0, 30)]):
        objs[f'parapet2{i}'] = ('stone_course',
                                box(f'parapet2{i}', a, 11.85, L2 + 0.22, b, 12.5, L2 + 1.0))
    objs['stair2'] = ('stone_course', stair('stair2', -4.5, 9.6, 7.0, 12.4, LEVEL, L2, 5))
    objs['cheek2l'] = ('quay_block', box('cheek2l', -4.9, 9.6, LEVEL - 0.4, -4.5, 12.4, L2 + 0.2))
    objs['cheek2r'] = ('quay_block', box('cheek2r', 7.0, 9.6, LEVEL - 0.4, 7.4, 12.4, L2 + 0.2))

    # --- the dominant mass, terminating the axis, two levels above the entrance (LM-2)
    b2, r2 = house('civic', -8.0, 15.0, 10.0, 26.0, L2, 3, 4.4)
    objs['civic_body'] = ('quay_block', b2)
    objs['civic_roof'] = ('shingle', r2)
    # secondary masses flanking it, so the dominant is not alone (MA-4)
    for i, (x0, x1) in enumerate([(-26, -12.0), (14.0, 28)]):
        body, roof = house(f't{i}', x0, 14.0, x1, 22.0, L2, 2, 2.4)
        objs[f't{i}_body'] = ('plaster_timber' if i % 2 else 'brick', body)
        objs[f't{i}_roof'] = ('shingle', roof)

    return objs


# ------------------------------------------------------------------ materials

def uv_by_world(ob, texel_m):
    """Cube-project and scale UVs by world size so texel density is a constant,
    not something that drifts per object. This is what stops the pixel scale
    from going inconsistent across a map."""
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co
            if ax == 0:   u, v = co.y, co.z
            elif ax == 1: u, v = co.x, co.z
            else:         u, v = co.x, co.y
            l[uv].uv = (u / texel_m, v / texel_m)
    bm.to_mesh(me); bm.free()


def grey_material():
    m = bpy.data.materials.new('clay')
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.62, 0.61, 0.60, 1)
    b.inputs['Roughness'].default_value = 0.72
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = 0.18
    return m


def pixel_material(name, texel_m):
    path = os.path.join(TEX, name + '.png')
    m = bpy.data.materials.new('px_' + name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(path)
    img.interpolation = 'Closest'          # non-negotiable: no bilinear on pixel art
    img.extension = 'REPEAT'
    nt.links.new(img.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.85
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = 0.10
    return m


TEXEL = {'cobble': 2.0, 'dirt': 3.0, 'stone_course': 2.0, 'quay_block': 2.4,
         'brick': 1.6, 'shingle': 1.6, 'plaster_timber': 3.0, 'plank': 1.4}


def apply_materials(objs, textured):
    clay = grey_material()
    cache = {}
    for key, (texname, ob) in objs.items():
        uv_by_world(ob, TEXEL[texname])
        ob.data.materials.clear()
        if textured:
            if texname not in cache:
                cache[texname] = pixel_material(texname, TEXEL[texname])
            ob.data.materials.append(cache[texname])
        else:
            ob.data.materials.append(clay)


# ------------------------------------------------------------------ camera / light

def setup_camera():
    """The Octopath camera: PERSPECTIVE, low downward pitch, facades frontal and
    parallel to the screen edge. Measured focus band sits at y=47% of frame."""
    cam_d = bpy.data.cameras.new('cam')
    cam_d.lens = 45
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    cam.location = Vector((0.0, -50.0, 40.0))
    cam.rotation_euler = (math.radians(60.5), 0.0, 0.0)   # 29.5 deg below horizontal
    bpy.context.scene.camera = cam
    return cam


def setup_light(rig):
    """rig='flat' = the honest clay test. rig='key' = the Octopath light."""
    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    if rig == 'flat':
        bg.inputs[0].default_value = (0.55, 0.55, 0.57, 1)
        bg.inputs[1].default_value = 1.0
        sun_d = bpy.data.lights.new('sun', 'SUN')
        sun_d.energy = 1.6
        sun_d.angle = math.radians(12)
        sun = bpy.data.objects.new('sun', sun_d)
        bpy.context.collection.objects.link(sun)
        sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    else:
        # cool ambient, so shadows go blue - the other half of the warm/cool split
        bg.inputs[0].default_value = (0.055, 0.075, 0.125, 1)
        bg.inputs[1].default_value = 1.0
        sun_d = bpy.data.lights.new('sun', 'SUN')
        sun_d.energy = 5.2
        sun_d.color = (1.0, 0.86, 0.66)               # warm key
        sun_d.angle = math.radians(2.5)               # hard shadow
        sun = bpy.data.objects.new('sun', sun_d)
        bpy.context.collection.objects.link(sun)
        sun.rotation_euler = (math.radians(52), 0, math.radians(28))
        fill_d = bpy.data.lights.new('fill', 'SUN')
        fill_d.energy = 0.6
        fill_d.color = (0.55, 0.68, 1.0)
        fill = bpy.data.objects.new('fill', fill_d)
        bpy.context.collection.objects.link(fill)
        fill.rotation_euler = (math.radians(120), 0, math.radians(-150))


def render(path, samples=48):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = samples
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 900
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    bpy.ops.render.render(write_still=True)


def tri_count():
    n = 0
    for ob in bpy.context.scene.objects:
        if ob.type == 'MESH':
            ob.data.calc_loop_triangles()
            n += len(ob.data.loop_triangles)
    return n


def stage(tag, textured, rig):
    wipe()
    objs = build_block()
    apply_materials(objs, textured)
    setup_camera()
    setup_light(rig)
    n = tri_count()
    p = os.path.join(HERE, OUT, tag + '.png')
    render(p)
    print(f'[octoblock] {tag:22s} {n:6d} triangles  -> {p}')
    return n


if __name__ == '__main__':
    n = stage('1-grey-flat', False, 'flat')
    stage('2-grey-lit', False, 'key')
    stage('3-textured', True, 'key')
    print(f'[octoblock] WHOLE SCENE = {n} triangles.')
    print('[octoblock] for scale: facade.py emits 15,284 faces for ONE facade wall.')
