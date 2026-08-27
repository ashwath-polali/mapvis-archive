"""MAPVIS FACADE — architectural articulation at real density, generated not modelled.

THE MEASURED PROBLEM this exists to solve:

    Kenney castle gate                     292 faces
    KayKit wall                            311
    Modular Village arch                 1,228
    NVIDIA ORCA Bistro, one city block  2,829,873   <- the only one whose GREY reads

Two to three orders of magnitude. A KayKit wall is a box with recesses. A Bistro window is a
modelled surround with a sill, mullions, a lintel and a reveal, and that is why one looks designed
and the other looks like a prototype.

You cannot hand-model your way across that gap. But you do not have to, because architectural
detail is not sculpted — it is a PROFILE RUN ALONG A PATH. A cornice, a sill, an architrave, a
string course, a plinth, a rake, a nosing: all of them are a drawn section extruded along a line.
That is literally how they are made in stone and in timber. So the whole vocabulary is:

    profile + path            -> mouldings (sills, cornices, architraves, copings)
    array                     -> repetition (mullions, balusters, dentils, courses, joists)
    boolean                   -> openings (windows, doors, arches, niches)
    bevel                     -> the arris that makes any of it catch light

None of that requires a model to decide anything. The only inputs are dimensions.

    blender -b -P mapvis/facade.py -- [--bays=3] [--floors=3] [--out=FILE]
"""
import math
import os
import sys

import bmesh
import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "mapwright", "modules"))
try:
    import mw_look
except ImportError:
    mw_look = None

bpy.ops.wm.read_factory_settings(use_empty=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(f, d=None):
    for a in ARGS:
        if a.startswith(f + "="):
            return a.split("=", 1)[1]
    return d


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------
def _obj(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def box(name, x, y, z, sx, sy, sz, bev=0.018):
    x0, x1 = x - sx / 2, x + sx / 2
    y0, y1 = y - sy / 2, y + sy / 2
    z0, z1 = z, z + sz
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = _obj(name, v, f)
    if bev:
        m = ob.modifiers.new("b", "BEVEL")
        m.width, m.segments, m.limit_method = bev, 2, "ANGLE"
        m.angle_limit = math.radians(50)
    return ob


def run(name, profile, a, b, bev=0.012):
    """Run a 2D PROFILE from point a to point b. The whole moulding vocabulary is this function.

    profile is a list of (u, v) in the section plane: u across the run, v along it.
    """
    ax, ay, az = a
    bx, by, bz = b
    d = mathutils.Vector((bx - ax, by - ay, bz - az))
    L = d.length
    if L < 1e-6:
        return None
    fwd = d.normalized()
    up = mathutils.Vector((0, 0, 1))
    if abs(fwd.dot(up)) > 0.99:
        up = mathutils.Vector((0, 1, 0))
    side = fwd.cross(up).normalized()
    up = side.cross(fwd).normalized()

    verts, faces = [], []
    n = len(profile)
    for end, t in ((0, 0.0), (1, 1.0)):
        o = mathutils.Vector((ax, ay, az)) + d * t
        for (u, v) in profile:
            p = o + side * u + up * v
            verts.append((p.x, p.y, p.z))
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    ob = _obj(name, verts, faces)
    if bev:
        m = ob.modifiers.new("b", "BEVEL")
        m.width, m.segments, m.limit_method = bev, 2, "ANGLE"
        m.angle_limit = math.radians(45)
    return ob


# real section profiles, drawn as they are drawn in a construction detail
P_SILL = [(-0.055, 0.0), (0.16, 0.0), (0.16, 0.055), (0.13, 0.075),
          (0.13, 0.095), (-0.055, 0.115)]
P_ARCHITRAVE = [(-0.03, -0.075), (0.075, -0.075), (0.075, -0.045), (0.055, -0.03),
                (0.075, -0.012), (0.075, 0.045), (0.055, 0.062), (0.075, 0.075),
                (0.075, 0.09), (-0.03, 0.09)]
P_CORNICE = [(-0.05, 0.0), (0.10, 0.0), (0.14, 0.045), (0.14, 0.075), (0.25, 0.115),
             (0.25, 0.175), (0.21, 0.205), (-0.05, 0.205)]
P_STRING = [(-0.04, 0.0), (0.085, 0.0), (0.10, 0.035), (0.085, 0.075), (-0.04, 0.095)]
P_PLINTH = [(-0.05, 0.0), (0.14, 0.0), (0.14, 0.30), (0.10, 0.345), (0.10, 0.40), (-0.05, 0.40)]


# ---------------------------------------------------------------------------
# a window: the element that separates a prototype from a building
# ---------------------------------------------------------------------------
def window(x, z, w, h, wall_y, depth=0.34, lights_x=2, lights_z=3, arched=False):
    """A real opening: reveal, sill with a drip, moulded architrave both jambs and head,
    mullions and transoms, glazing bars, and a keystone if arched."""
    out = []
    y_face = wall_y - 0.0
    y_in = wall_y + depth

    # REVEAL — the depth of the opening. Four splayed faces, which is what makes a window
    # read as a hole in a thick wall rather than a decal.
    for (a, b) in (((x - w / 2, z), (x - w / 2, z + h)),
                   ((x + w / 2, z), (x + w / 2, z + h)),
                   ((x - w / 2, z), (x + w / 2, z)),
                   ((x - w / 2, z + h), (x + w / 2, z + h))):
        v = [(a[0], y_face, a[1]), (b[0], y_face, b[1]),
             (b[0], y_in, b[1]), (a[0], y_in, a[1])]
        out.append(_obj("reveal", v, [(0, 1, 2, 3)]))

    # SILL — projects, with a drip on the underside so water does not run back
    out.append(run("sill", P_SILL, (x - w / 2 - 0.11, y_face, z - 0.115),
                   (x + w / 2 + 0.11, y_face, z - 0.115)))
    # ARCHITRAVE — the moulded surround, three runs mitred at the corners
    out.append(run("arch-l", P_ARCHITRAVE, (x - w / 2 - 0.06, y_face, z),
                   (x - w / 2 - 0.06, y_face, z + h + 0.06)))
    out.append(run("arch-r", P_ARCHITRAVE, (x + w / 2 + 0.06, y_face, z),
                   (x + w / 2 + 0.06, y_face, z + h + 0.06)))
    out.append(run("arch-head", P_ARCHITRAVE, (x - w / 2 - 0.09, y_face, z + h + 0.06),
                   (x + w / 2 + 0.09, y_face, z + h + 0.06)))
    # a cornice hood over the head, on brackets
    out.append(run("hood", P_CORNICE, (x - w / 2 - 0.16, y_face, z + h + 0.13),
                   (x + w / 2 + 0.16, y_face, z + h + 0.13)))
    for s in (-1, 1):
        out.append(box("bracket", x + s * (w / 2 + 0.10), y_face - 0.055, z + h + 0.02,
                       0.09, 0.13, 0.13))
    if arched:
        out.append(box("keystone", x, y_face - 0.05, z + h + 0.02, 0.17, 0.14, 0.26))

    # FRAME, MULLIONS, TRANSOMS, GLAZING BARS — the fine grid that reads at distance as texture
    fy = y_in - 0.055
    out.append(box("frame-b", x, fy, z + 0.02, w - 0.03, 0.075, 0.075, 0.008))
    out.append(box("frame-t", x, fy, z + h - 0.095, w - 0.03, 0.075, 0.075, 0.008))
    for s in (-1, 1):
        out.append(box("frame-s", x + s * (w / 2 - 0.035), fy, z + 0.02, 0.07, 0.075, h - 0.04,
                       0.008))
    for i in range(1, lights_x):
        out.append(box("mullion", x - w / 2 + w * i / lights_x, fy, z + 0.05, 0.055, 0.065,
                       h - 0.10, 0.006))
    for i in range(1, lights_z):
        out.append(box("transom", x, fy, z + h * i / lights_z, w - 0.08, 0.06, 0.045, 0.006))
    return [o for o in out if o]


def facade(bays=3, floors=3, bay_w=2.6, floor_h=3.4, wall_t=0.55):
    """A run of wall with real openings, a plinth, string courses at every floor, and a crowning
    cornice. Every part is a profile run or an array; nothing is sculpted."""
    W = bays * bay_w
    H = floors * floor_h
    out = []

    core = box("wall", W / 2, wall_t / 2, 0.0, W, wall_t, H, 0.02)
    out.append(core)
    # CUT the openings before anything else. Until the wall is actually pierced, a window is a
    # recessed panel, not a hole, and no amount of surround makes it read.
    cutters = []
    for f in range(floors):
        for b in range(bays):
            cx = bay_w * (b + 0.5)
            wz = f * floor_h + 0.95
            wh = floor_h - 1.75
            ww = bay_w - 1.15
            c = box("cut", cx, wall_t / 2, wz, ww, wall_t * 2.4, wh, 0.0)
            c.display_type = "WIRE"
            cutters.append(c)
    for c in cutters:
        m = core.modifiers.new("cut", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.object = c
        m.solver = "EXACT"
    out.append(run("plinth", P_PLINTH, (-0.02, 0.0, 0.0), (W + 0.02, 0.0, 0.0)))
    for f in range(1, floors):
        out.append(run(f"string{f}", P_STRING, (-0.02, 0.0, f * floor_h - 0.16),
                       (W + 0.02, 0.0, f * floor_h - 0.16)))
    out.append(run("cornice", P_CORNICE, (-0.09, 0.0, H - 0.30), (W + 0.09, 0.0, H - 0.30)))
    # dentils under the cornice: an array of small blocks, the classic shadow-maker
    nd = int(W / 0.28)
    for i in range(nd):
        out.append(box("dentil", 0.14 + i * 0.28, -0.10, H - 0.42, 0.135, 0.115, 0.115, 0.006))

    for f in range(floors):
        for b in range(bays):
            cx = bay_w * (b + 0.5)
            wz = f * floor_h + 0.95
            wh = floor_h - 1.75
            ww = bay_w - 1.15
            out += window(cx, wz, ww, wh, 0.0, depth=wall_t * 0.62,
                          lights_x=2, lights_z=3, arched=(f == 0))
    return out


def main():
    bays = int(opt("--bays", "3"))
    floors = int(opt("--floors", "3"))
    objs = facade(bays, floors)

    # apply modifiers so the face count reported is the real one
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            continue
        bpy.context.view_layer.objects.active = ob
        for m in list(ob.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
            except Exception:
                pass
    for ob in [o for o in bpy.data.objects if o.name.startswith("cut")]:
        bpy.data.objects.remove(ob, do_unlink=True)
    total = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    nwin = bays * floors
    print(f"FACADE: {bays} bays x {floors} floors, {len(bpy.data.objects)} parts, "
          f"{total} faces  ({total // max(1, nwin)} per window bay)")

    clay = bpy.data.materials.new("clay")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.62, 0.62, 0.61, 1)
    b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    for me in bpy.data.meshes:
        me.materials.clear()
        me.materials.append(clay)

    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.clip_start = 0.1
    cam.data.clip_end = 10000
    sc.camera = cam
    el, az = math.radians(24.0), math.radians(20.0)
    d = mathutils.Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    fwd = (-d).normalized()
    W = bays * 2.6
    Hh = floors * 3.4
    look = mathutils.Vector((W / 2, 0.2, Hh * 0.45))
    cam.data.ortho_scale = max(W, Hh) * 1.25
    cam.location = look - fwd * 500
    cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = 1800
    sc.render.resolution_y = 1500
    if mw_look:
        mw_look.apply_render(sc, transparent=False)
        mw_look.apply_light(sc, {"sun": {"azimuth": 318, "elevation": 34, "color": "#ffffff"}})
        sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.28
    sc.render.film_transparent = False
    sc.render.filepath = opt("--out", os.path.join(HERE, "facade.png"))
    bpy.ops.render.render(write_still=True)
    print("FACADE OK ->", sc.render.filepath)


main()
