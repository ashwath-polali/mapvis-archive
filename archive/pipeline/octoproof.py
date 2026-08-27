"""
octoproof.py - render SQUARE ENIX'S OWN shipped Octopath geometry, naked grey.

This is the acceptance-test experiment, run against the reference itself instead
of against us. If Octopath's own mesh fails the "strip everything, the naked grey
must read as a professionally designed place" test, then that test cannot be the
gate, because the thing it is meant to measure up to does not pass it.

Renders the same mesh three ways from one camera:
    A  flat unlit grey        - L3 exactly as written today
    B  clay + one key + AO    - what the industry actually reviews a blockout in
    C  its real shipped texture

Source: The Models Resource, Octopath Traveler (PC) - ripped by third parties,
used here only as a measuring stick, never shipped.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P octoproof.py -- --obj <path> --tag auction
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


OBJ = os.path.abspath(arg('--obj'))
TAG = arg('--tag', 'octo')
OUT = arg('--out', 'shots')
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, OUT), exist_ok=True)


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=OBJ)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    tris = 0
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
    return meshes, tris, lo, hi


def strip_to(meshes, mode):
    """mode 'grey' replaces every material with flat clay; 'texture' keeps the
    shipped material but kills specular so we compare albedo, not gloss."""
    if mode == 'grey':
        m = bpy.data.materials.new('clay')
        m.use_nodes = True
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Base Color'].default_value = (0.62, 0.61, 0.60, 1)
        b.inputs['Roughness'].default_value = 0.75
        if 'Specular IOR Level' in b.inputs:
            b.inputs['Specular IOR Level'].default_value = 0.15
        for o in meshes:
            o.data.materials.clear()
            o.data.materials.append(m)
    else:
        # Rebuild the material from map_Kd directly. Relying on the OBJ importer to
        # resolve it silently gives a magenta missing-texture render.
        base = os.path.dirname(OBJ)
        diffuse = None
        for f in sorted(os.listdir(base)):
            if f.lower().endswith('_cl.png') and 'room' in f.lower():
                diffuse = os.path.join(base, f)
        if diffuse is None:
            for f in sorted(os.listdir(base)):
                if f.lower().endswith('_cl.png'):
                    diffuse = os.path.join(base, f)
                    break
        m = bpy.data.materials.new('shipped')
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes['Principled BSDF']
        img = nt.nodes.new('ShaderNodeTexImage')
        img.image = bpy.data.images.load(diffuse)
        img.interpolation = 'Closest'          # pixel art: never bilinear
        img.extension = 'REPEAT'
        nt.links.new(img.outputs['Color'], b.inputs['Base Color'])
        b.inputs['Roughness'].default_value = 0.9
        if 'Specular IOR Level' in b.inputs:
            b.inputs['Specular IOR Level'].default_value = 0.05
        print(f'[octoproof] bound shipped texture {os.path.basename(diffuse)}')
        for o in meshes:
            o.data.materials.clear()
            o.data.materials.append(m)


def camera(lo, hi, lens=52, pitch_deg=28.0):
    """Octopath camera: perspective, low downward pitch, facade frontal."""
    ctr = (lo + hi) / 2
    size = max((hi - lo).x, (hi - lo).z, (hi - lo).y * 0.6)
    dist = size * 1.5
    p = math.radians(pitch_deg)
    cam_d = bpy.data.cameras.new('cam')
    cam_d.lens = lens
    # the rip is in centimetres, so the default 100-unit far clip hides everything
    cam_d.clip_start = max(0.1, size * 0.001)
    cam_d.clip_end = size * 20.0
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    cam.location = ctr + Vector((0, -dist * math.cos(p), dist * math.sin(p)))
    cam.rotation_euler = (math.radians(90) - p, 0, 0)
    bpy.context.scene.camera = cam


def light(mode):
    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    if mode == 'flat':
        # even ambient, no key, no AO. L3 as literally written.
        bg.inputs[0].default_value = (0.75, 0.75, 0.76, 1)
        bg.inputs[1].default_value = 1.2
        return
    bg.inputs[0].default_value = (0.06, 0.08, 0.13, 1)
    sun_d = bpy.data.lights.new('sun', 'SUN')
    sun_d.energy = 5.0
    sun_d.color = (1.0, 0.87, 0.68)
    sun_d.angle = math.radians(2.0)
    sun = bpy.data.objects.new('sun', sun_d)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), 0, math.radians(30))
    fill_d = bpy.data.lights.new('fill', 'SUN')
    fill_d.energy = 0.7
    fill_d.color = (0.55, 0.68, 1.0)
    fill = bpy.data.objects.new('fill', fill_d)
    bpy.context.collection.objects.link(fill)
    fill.rotation_euler = (math.radians(115), 0, math.radians(-150))


def render(path):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 64
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 900
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def run(stage_tag, mode, lighting):
    meshes, tris, lo, hi = load()
    strip_to(meshes, mode)
    camera(lo, hi)
    light(lighting)
    p = os.path.join(HERE, OUT, f'{TAG}-{stage_tag}.png')
    render(p)
    d = hi - lo
    print(f'[octoproof] {TAG}-{stage_tag}: {tris} tris  bbox {d.x:.1f} x {d.y:.1f} x {d.z:.1f}  -> {p}')
    return tris, d


if __name__ == '__main__':
    tris, d = run('A-flat-grey', 'grey', 'flat')
    run('B-clay-lit', 'grey', 'key')
    run('C-shipped-texture', 'texture', 'key')
    area = d.x * d.y
    print(f'[octoproof] {tris} triangles over {area:.0f} m2 = {tris / max(area, 1):.2f} tris/m2')
