"""MAPVIS KIT v2 — architecture built with Blender's real modelling toolkit, not hand-written quads.

Why v1 looked like cardboard, and this is the whole lesson:

    EVERY EDGE IN v1 WAS A PERFECT 90 DEGREES.

Nothing in the physical world has a zero-radius edge. A stone arris is chipped, a coping is
weathered, a timber is planed. A sharp edge catches no light at all, so a CG object made of them
reads as flat paper no matter how correct its proportions are. The single highest-value operation in
3D is BEVEL, and v1 used none.

This module builds real Blender objects with real modifiers:
    bevel      the chamfer that makes an edge catch light. Applied to everything, always.
    array      repetition without hand-writing every instance (courses, merlons, balusters)
    solidify   thickness from a surface
    bmesh      inset / extrude / bridge for panelling and recesses
    curve+profile  a moulding swept along a path, which is how a cornice is actually made

Units are metres. A person is 1.7 m.
"""
import bmesh
import bpy
import mathutils

BEVEL_W = 0.035          # ~35 mm arris. Small. It is the difference between stone and paper.
BEVEL_SEG = 2


# ---------------------------------------------------------------------------
def _new(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def cube(name, cx, cy, cz, sx, sy, sz):
    """a box as a real object, ready for modifiers"""
    x0, x1 = cx - sx / 2, cx + sx / 2
    y0, y1 = cy - sy / 2, cy + sy / 2
    z0, z1 = cz, cz + sz
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _new(name, v, f)


def bevel(ob, width=BEVEL_W, segments=BEVEL_SEG, angle=50.0):
    """THE operation. Without it nothing reads as a solid."""
    m = ob.modifiers.new("bev", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = angle * 3.14159265 / 180.0
    m.harden_normals = False
    return ob


def array(ob, count, offset, use_relative=False):
    m = ob.modifiers.new("arr", "ARRAY")
    m.count = count
    m.use_relative_offset = use_relative
    m.use_constant_offset = not use_relative
    if not use_relative:
        m.constant_offset_displace = offset
    else:
        m.relative_offset_displace = offset
    return ob


def solidify(ob, thickness, offset=-1.0):
    m = ob.modifiers.new("sol", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    return ob


def inset_faces(ob, thickness, depth=0.0, individual=True):
    """recess or emboss every face — panelling, window reveals, recessed courses"""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.inset_individual(bm, faces=bm.faces[:], thickness=thickness,
                               depth=depth) if individual else \
        bmesh.ops.inset_region(bm, faces=bm.faces[:], thickness=thickness, depth=depth)
    bm.to_mesh(me)
    bm.free()
    return ob


def moulding(name, path_pts, profile_pts, tilt=0.0):
    """Sweep a PROFILE along a PATH. This is how a cornice, a coping, a handrail, a stair nosing
    and a string course are actually made — as a drawn section run along a line. Hand-writing them
    as boxes is why v1's trim read as slabs."""
    pc = bpy.data.curves.new(name + "-prof", "CURVE")
    pc.dimensions = "2D"
    sp = pc.splines.new("POLY")
    sp.points.add(len(profile_pts) - 1)
    for i, (x, y) in enumerate(profile_pts):
        sp.points[i].co = (x, y, 0, 1)
    sp.use_cyclic_u = True
    prof = bpy.data.objects.new(name + "-prof", pc)
    bpy.context.collection.objects.link(prof)
    prof.hide_render = True

    c = bpy.data.curves.new(name + "-path", "CURVE")
    c.dimensions = "3D"
    s = c.splines.new("POLY")
    s.points.add(len(path_pts) - 1)
    for i, p in enumerate(path_pts):
        s.points[i].co = (p[0], p[1], p[2], 1)
    c.bevel_mode = "OBJECT"
    c.bevel_object = prof
    c.use_fill_caps = True
    ob = bpy.data.objects.new(name, c)
    bpy.context.collection.objects.link(ob)
    return ob


def set_mat(ob, mat):
    ob.data.materials.append(mat)
    return ob


# ---------------------------------------------------------------------------
# LAYER 2 — a retaining wall, built properly
# ---------------------------------------------------------------------------
def retaining_wall(x0, x1, y, z_bot, z_top, mat_stone, mat_trim, face=-1,
                   course_h=0.55, buttress_every=7.5):
    """Real construction, real modifiers.

    - the wall CORE is a solid with a batter, bevelled
    - COURSES are an arrayed proud band, each one bevelled, so the wall has actual relief
    - the COPING is a swept moulding, not a box
    - BUTTRESSES are arrayed, tapered, bevelled
    Returns the list of objects.
    """
    out = []
    L = x1 - x0
    h = z_top - z_bot
    cx = (x0 + x1) / 2
    batter = h / 14.0

    core = cube("wall-core", cx, y + face * 0.55, z_bot, L, 1.10, h - 0.30)
    # taper the top toward the retained side: a real battered wall
    for v in core.data.vertices:
        if v.co.z > z_bot + h * 0.5:
            v.co.y -= face * batter
    bevel(core, 0.05, 2)
    set_mat(core, mat_stone)
    out.append(core)

    # COURSES, as individual stones with STAGGERED VERTICAL JOINTS.
    # A continuous horizontal band is a radiator, not masonry. What makes stone read as stone is
    # the vertical joint, offset half a stone every course, so the eye sees a bond pattern instead
    # of corrugation. Two arrays: stones along X, courses up Z, one set offset by half a stone.
    stone_l = 1.05
    joint = 0.035
    n = max(2, int((h - 0.95) / course_h))
    ncol = max(2, int(L / stone_l))
    for parity in (0, 1):
        rows = (n + 1 - parity) // 2
        if rows < 1:
            continue
        x_off = (stone_l / 2.0) * parity
        blk = cube(f"wall-stone{parity}", x0 + stone_l / 2 + x_off, y + face * 1.14,
                   z_bot + 0.50 + parity * course_h,
                   stone_l - joint, 0.15, course_h - joint)
        bevel(blk, 0.022, 2)
        array(blk, ncol, (stone_l, 0, 0))
        m2 = blk.modifiers.new("arr2", "ARRAY")
        m2.count = rows
        m2.use_relative_offset = False
        m2.use_constant_offset = True
        m2.constant_offset_displace = (0, face * -(batter / max(n, 1)) * 2.0, course_h * 2)
        set_mat(blk, mat_stone)
        out.append(blk)

    # footing: a proud plinth with its own bevel
    foot = cube("wall-foot", cx, y + face * 1.24, z_bot, L + 0.10, 0.42, 0.72)
    bevel(foot, 0.05, 2)
    set_mat(foot, mat_trim)
    out.append(foot)

    # coping: a SWEPT MOULDING with a drip and a weathered top, not a slab
    cy = y + face * (1.10 - batter)
    prof = [(-0.34, 0.0), (0.34, 0.0), (0.30, 0.13), (0.24, 0.17),
            (0.24, 0.30), (-0.24, 0.34), (-0.30, 0.20)]
    cop = moulding("wall-coping", [(x0 - 0.15, cy, z_top - 0.30), (x1 + 0.15, cy, z_top - 0.30)],
                   prof)
    set_mat(cop, mat_trim)
    out.append(cop)

    # buttresses: tapered piers, arrayed, each capped with a weathering
    nb = max(1, int(L // buttress_every))
    if nb >= 1 and L > buttress_every:
        step = L / (nb + 1)
        bh = h * 0.72
        bt = cube("wall-butt", x0 + step, y + face * 1.55, z_bot, 1.25, 0.95, bh)
        for v in bt.data.vertices:
            if v.co.z > z_bot + bh * 0.5:
                v.co.y -= face * 0.16
                v.co.x += -0.10 if v.co.x < x0 + step else 0.10
        bevel(bt, 0.05, 2)
        array(bt, nb, (step, 0, 0))
        set_mat(bt, mat_stone)
        out.append(bt)

        cap = cube("wall-buttcap", x0 + step, y + face * 1.50, z_bot + bh, 1.35, 1.05, 0.34)
        for v in cap.data.vertices:
            if v.co.z > z_bot + bh + 0.17:
                v.co.y -= face * 0.30
        bevel(cap, 0.04, 2)
        array(cap, nb, (step, 0, 0))
        set_mat(cap, mat_trim)
        out.append(cap)

    return out
