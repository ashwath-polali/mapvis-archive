"""
ops_solid.py - subtraction and the non-monotonic operators.

Why this file exists. docs/THE-PICTURE.md section 6 is the largest itemised diagnosis
in this project: the pipeline can only push a plan polygon up, extrusion is MONOTONIC
IN Z, and almost nothing in the reference set is. No overhang, no undercut, no battered
lean, no jettied floor, no subtraction (an arch is a HOLE you see water through, a dock
is a NOTCH cut out of stone), no undersides, no two walkable heights over one XY, no
ceiling, no catenary, no detached airborne mass. Those are not "harder to build" in a
heightfield pipeline, they are unrepresentable.

Ten operations, each a real named thing a builder or a landform does, each parametric:

    carve        boolean difference - a street out of a block, a notch out of a quay
    pierce       a hole you see THROUGH, with real reveal faces
    overhang     upper levels project outward - jetty, mushroom rock, mesa plate
    batter       a face that leans as it rises
    cantilever   a deck past its support, with joists and soffit modelled
    undercroft   an arcaded space beneath a walkable surface, open at the sides
    catenary     a line that sags
    shelf_stack  the measured Octopath scenery cliff: 5-7 shelves with drip lips
    two_level    two walkable surfaces over one XY, upper underside visible

CSG goes through Blender's Boolean modifier on the EXACT solver, never FAST. Measured
here on a wall whose cutting tool is EXACTLY coplanar with both wall faces: EXACT gives
12 polygons and a clean four-face reveal, FAST gives 18 polygons, leaves a membrane the
ray passes 16 faces through, and silently drops the operand material. So EXACT, with
`nudge` available to pre-offset the tool along its own vertex normals when a caller has
to fall back to FAST.

Everything that is not CSG is pure kit/_geom and needs no Blender at all.

CHAR = 1.7 m is the yardstick and kit/_geom.check_char is the gate. One level is
exactly 1.0 CHAR. Where a band is MEASURED it says so and cites where; where it is only
a structural sanity limit it says that instead.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P ops_solid.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "kit"))

import _geom as _g                                            # noqa: E402
from _geom import CHAR, Mesh, check_char                      # noqa: E402

try:
    import bpy
    import bmesh
except ImportError:                       # importable and testable without Blender;
    bpy = bmesh = None                    # only carve/pierce and their callers need it

LEVEL = CHAR                              # one walkable level, exactly 1.0 CHAR

# MEASURED, STATE.md section 4 and docs/THE-PICTURE.md:
#   level        1.0 CHAR (not 1.5, not 1.9)
#   shelf        0.6-0.8 CHAR per shelf, 5-7 shelves      (EL-9 scenery cliff)
#   door         1.0 x 2.0 CHAR                           (L3 known-size vocabulary)
#   rope sag     8-14% of span                            (_geom.sag_curve)
# LIMIT, structural sanity only, NOT measured off the reference set:
#   batter lean  0.5-18 deg
#   cantilever   backspan >= 2 x reach (timber joist rule)
#   arcade bay   1.0-4.0 CHAR clear, pier 0.25-1.0 CHAR
#   headroom     >= 1.2 CHAR under a walkable deck
SHELF_H_CHAR = (0.6, 0.8)
SHELF_N = (5, 7)
SAG_RATIO = (0.04, 0.20)
LEAN_DEG = (0.5, 18.0)
HEADROOM_CHAR = 1.2


class SolidError(ValueError):
    """Raised when an operator is handed something CSG or a sweep cannot survive."""


# ---------------------------------------------------------------------------
# measurement - the asserts, and the only honest way to say an op did its job
# ---------------------------------------------------------------------------
def triangles(mesh):
    """Fan triangulation. Safe here because every mesh that has been through carve()
    is triangulated on the way out - a boolean emits concave C-shaped ngons and fanning
    one covers the hole it was supposed to leave (measured: 5 spurious ray crossings
    through a real window before the output was triangulated)."""
    return [(mesh.v[f[0]], mesh.v[f[i]], mesh.v[f[i + 1]])
            for f in mesh.f for i in range(1, len(f) - 1)]


def ray_crossings(mesh, origin, direction):
    """Moller-Trumbore, counting only t > 0. Zero means you can see straight through,
    which is the only mechanical test of "is there a real hole here"."""
    ox, oy, oz = origin
    L = math.sqrt(sum(c * c for c in direction)) or 1.0
    dx, dy, dz = (c / L for c in direction)
    n = 0
    for (a, b, c) in triangles(mesh):
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        px = dy * e2[2] - dz * e2[1]
        py = dz * e2[0] - dx * e2[2]
        pz = dx * e2[1] - dy * e2[0]
        det = e1[0] * px + e1[1] * py + e1[2] * pz
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        t0 = (ox - a[0], oy - a[1], oz - a[2])
        u = (t0[0] * px + t0[1] * py + t0[2] * pz) * inv
        if u < -1e-9 or u > 1 + 1e-9:
            continue
        qx = t0[1] * e1[2] - t0[2] * e1[1]
        qy = t0[2] * e1[0] - t0[0] * e1[2]
        qz = t0[0] * e1[1] - t0[1] * e1[0]
        v = (dx * qx + dy * qy + dz * qz) * inv
        if v < -1e-9 or u + v > 1 + 1e-9:
            continue
        if (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv > 1e-7:
            n += 1
    return n


def face_normal(pts):
    """Newell, unit. Works on the slightly non-planar quads a sweep emits."""
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / L, ny / L, nz / L)


def undersides(mesh, above_z, min_nz=-0.5, min_area=0.02):
    """Faces that point DOWN and sit above `above_z`. An extrusion has exactly one such
    face, its own bottom cap at z_min, so a count above zero here IS non-monotonicity in
    Z. This is the single test that separates this module from the rest of the pipeline."""
    out = []
    for f in mesh.f:
        pts = [mesh.v[i] for i in f]
        if min(p[2] for p in pts) <= above_z:
            continue
        if face_normal(pts)[2] > min_nz:
            continue
        if _g._area(pts) < min_area:
            continue
        out.append(pts)
    return out


def _in_plan(pts, x, y):
    inside = False
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i][:2], pts[(i + 1) % n][:2]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
            inside = not inside
    return inside


def up_surfaces_at(mesh, x, y, min_nz=0.5):
    """z of every up-facing face whose plan projection contains (x, y). Two entries is
    the literal definition of two walkable heights over one XY, which a heightfield
    cannot represent at all."""
    zs = []
    for f in mesh.f:
        pts = [mesh.v[i] for i in f]
        if face_normal(pts)[2] < min_nz:
            continue
        if _in_plan(pts, x, y):
            zs.append(sum(p[2] for p in pts) / len(pts))
    return sorted(zs)


def volume(mesh):
    return _g.signed_volume(mesh)


def _offset_loop(poly, d):
    """Offset a CLOSED plan loop outward by d, mitred. _geom.offset_2d is open-path-only
    and offsets a loop's two end stations off the wrong normal, which tears the loop."""
    fr = _g.plan_frames([(p[0], p[1], 0.0) for p in poly], closed=True)
    return [(p[0] + nx * d * sc, p[1] + ny * d * sc)
            for p, (nx, ny, sc) in zip(poly, fr)]


def _rect(w, d, cx=0.0, cy=0.0):
    return [(cx - w / 2, cy - d / 2), (cx + w / 2, cy - d / 2),
            (cx + w / 2, cy + d / 2), (cx - w / 2, cy + d / 2)]


# ---------------------------------------------------------------------------
# CSG plumbing
# ---------------------------------------------------------------------------
def _need_bpy(op):
    if bpy is None:
        raise SolidError(f"{op}() needs Blender. Run under: blender -b -P <script>")


def _remat(mesh, name):
    out = Mesh()
    out.v = list(mesh.v)
    out.f = list(mesh.f)
    out.m = [name] * len(mesh.f)
    out.dropped = mesh.dropped
    return out


def _nudge(mesh, eps):
    """Push every vertex out along the accumulated vertex normal. Keyed on the ROUNDED
    position, because a _geom.Mesh is a face soup with no shared vertices: offsetting
    each face by its own normal would blow the tool apart into 6 loose quads and CSG on
    that produces silence, not an error."""
    acc = {}
    for f in mesh.f:
        pts = [mesh.v[i] for i in f]
        n = face_normal(pts)
        a = _g._area(pts)
        for p in pts:
            k = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
            v = acc.setdefault(k, [0.0, 0.0, 0.0])
            for j in range(3):
                v[j] += n[j] * a
    out = Mesh()
    out.f = list(mesh.f)
    out.m = list(mesh.m)
    for p in mesh.v:
        k = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
        n = acc.get(k, [0.0, 0.0, 0.0])
        L = math.sqrt(sum(c * c for c in n)) or 1.0
        out.v.append((p[0] + n[0] / L * eps, p[1] + n[1] / L * eps, p[2] + n[2] / L * eps))
    return out


def _to_object(mesh, name, weld=1e-6):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in mesh.v], [], [tuple(f) for f in mesh.f])
    me.validate(verbose=False)
    me.update()
    if len(me.polygons) != len(mesh.f):
        raise SolidError(f"{name}: Blender dropped {len(mesh.f) - len(me.polygons)} of "
                         f"{len(mesh.f)} faces on import, so the material map is invalid")
    ob = bpy.data.objects.new(name, me)
    slot = {}
    for mn in dict.fromkeys(mesh.m):
        slot[mn] = len(ob.data.materials)
        ob.data.materials.append(bpy.data.materials.get(mn) or bpy.data.materials.new(mn))
    for p, mn in zip(me.polygons, mesh.m):
        p.material_index = slot.get(mn, 0)
    bpy.context.scene.collection.objects.link(ob)
    if weld:                              # material_index is a face attribute and rides through
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
        bm.to_mesh(me)
        bm.free()
        me.update()
    return ob


def _boundary_edges(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bm.free()
    return n


def _from_object(ob):
    """Evaluate the modifier stack and come back as a _geom.Mesh, triangulating the
    ngons. Materials ride across because material_mode is TRANSFER, which is also the
    only combination that keeps the operand's name on the cut faces (measured)."""
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    names = [s.name for s in me.materials] or ["stone"]
    bm = bmesh.new()
    bm.from_mesh(me)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons)
    out = Mesh()
    for f in bm.faces:
        out.poly([tuple(v.co) for v in f.verts],
                 names[min(f.material_index, len(names) - 1)])
    bm.free()
    ev.to_mesh_clear()
    return out


def _boolean(solid, tool, op, solver, require_closed, use_self):
    A = _to_object(solid, "_csg_solid")
    B = _to_object(tool, "_csg_tool")
    try:
        if require_closed:
            for ob, label in ((A, "solid"), (B, "tool")):
                n = _boundary_edges(ob)
                if n:
                    raise SolidError(
                        f"{label} is an open shell ({n} boundary edges). CSG on an open "
                        f"shell produces garbage silently - fix the caller, do not "
                        f"relax this.")
        md = A.modifiers.new("csg", "BOOLEAN")
        md.operation = op
        md.object = B
        md.solver = solver
        md.material_mode = "TRANSFER"
        md.use_self = use_self
        return _from_object(A)
    finally:
        for ob in (A, B):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.meshes.remove(me)


# ---------------------------------------------------------------------------
# 1. carve
# ---------------------------------------------------------------------------
def carve(solid, tool, solver="EXACT", nudge=0.0, tool_mat=None,
          require_closed=True, use_self=True, into=None):
    """Boolean DIFFERENCE. A street cut out of a block, a dock notch cut out of a quay,
    a chamber cut out of rock, a chasm gouged across a platform.

    THE POINT: docs/THE-PICTURE.md section 6 item 2 - the composition of the reference
    set is repeatedly ABOUT THE VOID, and extrusion only produces mass. This is the
    operator the whole pipeline was missing.

    solver   EXACT always. Measured on a tool exactly coplanar with both faces of the
             wall it cuts: EXACT -> 12 polys, a clean 4-face reveal, operand material
             preserved. FAST -> 18 polys, a membrane left across the void (16 ray
             crossings where there should be 0), operand material silently dropped.
    nudge    metres to pre-offset the tool along its own vertex normals. Zero by
             default because EXACT does not need it; it is the escape hatch for a
             caller who has to use FAST on a huge scene.
    tool_mat repaints the tool so every cut face carries one name ("reveal"), which is
             what lets a downstream material pass find the soffits and jambs at all.

    Both operands must be CLOSED. That is checked, not trusted.
    """
    _need_bpy("carve")
    if tool_mat:
        tool = _remat(tool, tool_mat)
    if nudge:
        tool = _nudge(tool, nudge)
    out = _boolean(solid, tool, "DIFFERENCE", solver, require_closed, use_self)
    if into is not None:
        into.extend(out)
    return out


def fuse(a, b, solver="EXACT", require_closed=True, use_self=True, into=None):
    """Boolean UNION. Not one of the ten, but carve() requires a closed operand and an
    assembly that self-intersects has to be welded into one shell before it can be cut."""
    _need_bpy("fuse")
    out = _boolean(a, b, "UNION", solver, require_closed, use_self)
    if into is not None:
        into.extend(out)
    return out


# ---------------------------------------------------------------------------
# 2. pierce
# ---------------------------------------------------------------------------
# span/height bands in CHAR. door 1.0 x 2.0 CHAR is MEASURED (the L3 known-size
# vocabulary in docs/CONSTRUCTION-THEORY.md); a window cill sits 0.85-1.10 m above its
# OWN floor (STATE.md section 4). Every other band here is a structural sanity limit.
OPENING_KINDS = {
    "door":    dict(span=1.00 * CHAR, height=2.00 * CHAR, head="flat",
                    z_sill=0.0, span_b=(0.7, 1.4), h_b=(1.6, 2.4)),
    "window":  dict(span=0.65 * CHAR, height=0.90 * CHAR, head="round",
                    z_sill=0.95, span_b=(0.35, 1.0), h_b=(0.5, 1.5)),
    "arch":    dict(span=2.20 * CHAR, height=2.60 * CHAR, head="round",
                    z_sill=0.0, span_b=(1.2, 4.0), h_b=(1.5, 4.5)),
    "gate":    dict(span=2.00 * CHAR, height=3.00 * CHAR, head="pointed",
                    z_sill=0.0, span_b=(1.4, 3.6), h_b=(1.8, 4.2)),
    "culvert": dict(span=1.10 * CHAR, height=1.30 * CHAR, head="segmental",
                    z_sill=0.0, span_b=(0.5, 2.6), h_b=(0.5, 2.6)),
    "tunnel":  dict(span=2.60 * CHAR, height=2.80 * CHAR, head="segmental",
                    z_sill=0.0, span_b=(1.4, 5.0), h_b=(1.5, 4.6)),
}


class Opening:
    """A void to be driven clean through a wall: arch, gate, door, window, culvert,
    tunnel mouth.

    Authored in its own frame - the span runs on X, the wall thickness on Y, the sill
    at z_sill - then placed with bearing_deg and origin exactly like every other element
    in the kit. The head curve comes from _geom.arc_intrados, so the ring, the barrel
    and the hood mould downstream are all struck off the same list of points.
    """

    def __init__(self, kind="arch", span=None, height=None, z_sill=None, head=None,
                 rise=None, segs=12, mat="reveal", bearing_deg=0.0,
                 origin=(0.0, 0.0, 0.0)):
        if kind not in OPENING_KINDS:
            raise SolidError(f"unknown opening kind {kind!r}; have {sorted(OPENING_KINDS)}")
        d = OPENING_KINDS[kind]
        self.kind = kind
        self.span = d["span"] if span is None else span
        self.height = d["height"] if height is None else height
        self.z_sill = d["z_sill"] if z_sill is None else z_sill
        self.head = d["head"] if head is None else head
        self.segs = segs
        self.mat = mat
        self.bearing_deg = bearing_deg
        self.origin = origin
        check_char(f"{kind} span", self.span, *d["span_b"])
        check_char(f"{kind} height", self.height, *d["h_b"])
        if self.head == "flat":
            self.rise = 0.0
        elif rise is not None:
            self.rise = rise
        else:
            self.rise = {"round": 0.50, "segmental": 0.26, "pointed": 0.72,
                         "ogee": 0.62}.get(self.head, 0.5) * self.span
        if self.rise > self.height - 0.05:
            raise SolidError(f"{kind}: rise {self.rise:.2f} m leaves no jamb under a "
                             f"{self.height:.2f} m head")

    def section(self):
        """The void in elevation, (x, z) about the opening centreline, CCW."""
        hw = self.span / 2.0
        spring = self.z_sill + self.height - self.rise
        pts = [(-hw, self.z_sill), (hw, self.z_sill)]
        if self.rise <= 1e-9:
            pts += [(hw, self.z_sill + self.height), (-hw, self.z_sill + self.height)]
            return pts
        pts.append((hw, spring))
        curve = _g.arc_intrados(self.span, self.rise, self.segs, self.head)
        pts += [(x, spring + z) for (x, z) in reversed(curve)]
        pts.append((-hw, spring))
        return _g.dedupe_2d(pts)

    def tool(self, depth):
        """The cutting solid: the section run through `depth`, centred on y = 0 and
        placed. `depth` must overshoot BOTH wall faces or the cut leaves a membrane.

        The section is REVERSED on the way in. _geom.extrude_y does not correct winding
        the way extrude_x does, and a CCW (x, z) section comes out inside-out: measured
        signed volume -269.41 m3 against +269.41 reversed. An inside-out tool is the
        worst possible CSG failure because the boolean succeeds and removes nothing -
        it cost three of the ten operations a silent no-op before this assert existed.
        """
        m = Mesh()
        _g.extrude_y(m, list(reversed(self.section())), -depth / 2.0, depth / 2.0,
                     mat=self.mat, closed=True, cap_a=True, cap_b=True)
        vol = _g.signed_volume(m)
        if vol <= 0:
            raise SolidError(f"{self.kind} tool is inside out (signed volume {vol:.2f}); "
                             f"CSG would silently remove nothing")
        m.v = _g.place(m.v, self.bearing_deg, self.origin)
        return m

    def centre(self):
        """World centre of the void - where the see-through ray is cast from."""
        z = self.z_sill + self.height * 0.45
        return _g.place([(0.0, 0.0, z)], self.bearing_deg, self.origin)[0]

    def axis(self):
        """World unit vector along the wall thickness."""
        a = math.radians(self.bearing_deg + 90.0)
        return (math.cos(a), math.sin(a), 0.0)


def pierce(wall, opening, depth=None, solver="EXACT", nudge=0.0, into=None):
    """A HOLE YOU CAN SEE THROUGH, with real reveal faces: arch, gate, window, culvert,
    tunnel mouth.

    docs/THE-PICTURE.md: "a bridge arch is a hole you see the water through". An extruded
    footprint has no way to state that. The returned wall carries a real void plus the
    jambs, soffit and cill the boolean leaves behind, all tagged `opening.mat` so a later
    material pass can find them.

    `depth` defaults to twice the wall's largest extent, which guarantees the tool exits
    both faces from any placement on the wall.
    """
    if depth is None:
        lo, hi = wall.bbox()
        depth = 2.0 * max(hi[i] - lo[i] for i in range(3))
    out = carve(wall, opening.tool(depth), solver=solver, nudge=nudge,
                tool_mat=opening.mat)
    if into is not None:
        into.extend(out)
    return out


# ---------------------------------------------------------------------------
# 3. overhang
# ---------------------------------------------------------------------------
def overhang(profile=None, per_level_offset=0.42, levels=3, level_h=LEVEL,
             mat="stone", soffit_mat="soffit", cap_top=True, into=None):
    """Upper levels project OUTWARD past the ones below: a jettied timber floor, a
    mushroom-capped sandstone rock, a mesa plate wider than its own base.

    Negative draft, so extrusion cannot make it at all and a heightfield cannot store it.
    Each jetty leaves a horizontal DOWN-FACING soffit ring between the level below and
    the level above, which is the face that makes the projection legible - without it a
    jetty reads as a bigger box.

    per_level_offset  metres each level oversails the one below; a scalar, or one value
                      per jetty. Outward is the right-hand plan normal of a CCW loop.
    level_h           1.0 CHAR. Gated: one level is exactly one CHAR, measured.
    """
    check_char("level_h", level_h, 1.0, 1.0)
    if levels < 2:
        raise SolidError("overhang needs at least 2 levels; 1 level is an extrusion")
    poly = _g.ensure_ccw(_rect(4.6, 3.8) if profile is None else list(profile))
    offs = ([per_level_offset] * (levels - 1) if not isinstance(per_level_offset, (list, tuple))
            else list(per_level_offset))
    if len(offs) != levels - 1:
        raise SolidError(f"overhang: {levels} levels needs {levels - 1} offsets, got {len(offs)}")
    m = into or Mesh()
    ring = [(p[0], p[1]) for p in poly]
    m.fan([(p[0], p[1], 0.0) for p in reversed(ring)], mat)
    for k in range(levels):
        z0, z1 = k * level_h, (k + 1) * level_h
        _g.ribbon(m, [(p[0], p[1], z0) for p in ring],
                  [(p[0], p[1], z1) for p in ring], mat, closed=True)
        if k < levels - 1:
            wider = _offset_loop(ring, offs[k])
            # inner -> outer at one z: t x (b - a) points DOWN. That is the soffit.
            _g.ribbon(m, [(p[0], p[1], z1) for p in ring],
                      [(p[0], p[1], z1) for p in wider], soffit_mat, closed=True)
            ring = wider
    if cap_top:
        m.fan([(p[0], p[1], levels * level_h) for p in ring], mat)
    return m


# ---------------------------------------------------------------------------
# 4. batter
# ---------------------------------------------------------------------------
def batter(profile=None, lean=6.0, height=2 * LEVEL, courses=4, mat="stone",
           cap_top=True, cap_bot=True, into=None):
    """A wall that LEANS as it rises. Positive lean sets back (the gravity-wall face of
    every retaining wall and sea wall in the reference set); negative lean throws the
    face outward, which is the defensive batter and is negative draft.

    Why this exists when _geom.prism already has scale_top: scale_top is a scale about
    the centroid, so on any plan that is not a centred square the lean angle differs
    edge by edge and the corners shear. This offsets every station along its own mitred
    plan normal, so the lean is the SAME measured angle on every face and the corners
    stay square - which is what a mason builds and what a silhouette reads.

    lean   degrees from vertical, 0.5-18. A structural sanity limit, not a measured band.
    """
    if abs(lean) < LEAN_DEG[0] or abs(lean) > LEAN_DEG[1]:
        raise SolidError(f"batter lean={lean} deg outside the buildable "
                         f"{LEAN_DEG[0]}-{LEAN_DEG[1]} deg")
    poly = _g.ensure_ccw(_rect(4.2, 3.2) if profile is None else list(profile))
    m = into or Mesh()
    t = math.tan(math.radians(lean))
    rings = []
    for i in range(courses + 1):
        z = height * i / courses
        rings.append([(p[0], p[1], z) for p in _offset_loop(poly, -t * z)])
    _g.loft(m, rings, mat, closed=True, cap_start=cap_bot, cap_end=cap_top)
    return m


# ---------------------------------------------------------------------------
# 5. cantilever
# ---------------------------------------------------------------------------
def cantilever(anchor=None, reach=2.6, joists=7, deck_t=0.11, joist_w=0.16,
               joist_h=0.30, backspan=None, nose=0.09, fascia_h=0.24,
               brace_every=2, brace_drop=1.15, support_h=2.0 * CHAR,
               mat="timber", deck_mat="deck", into=None):
    """A deck projecting past its support, WITH ITS UNDERSIDE AND JOISTS MODELLED.

    An entire reference town is this one operation: Crackridge is a timber deck hung
    over a canyon on trestles, and docs/THE-PICTURE.md lists "joists under a cantilevered
    deck" as one of the undersides extrusion has none of, because everything an extrusion
    makes rests on ground.

    anchor      ((x0,y0,z_deck), (x1,y1,z_deck)) - the top edge of the supporting mass.
                The deck projects to the RIGHT of travel, the kit's `side` convention.
    reach       metres past the support face.
    backspan    joist tail bearing back over the support. Defaults to 2 x reach and is
                gated there: a timber cantilever needs backspan >= 2 x reach or it
                levers its own fixing out. A structural rule, not a measured band.
    support_h   stub of the supporting mass, so the deck reads as HELD rather than
                floating. Pass 0 when the caller already owns the wall.
    """
    if anchor is None:
        anchor = ((0.0, -3.4, 2.0 * CHAR), (0.0, 3.4, 2.0 * CHAR))
    a, b = anchor
    z = a[2]
    run = math.dist(a[:2], b[:2])
    if run < 1e-6:
        raise SolidError("cantilever: anchor has zero length")
    backspan = 2.0 * reach if backspan is None else backspan
    if backspan < 2.0 * reach - 1e-9:
        raise SolidError(f"cantilever: backspan {backspan:.2f} m < 2 x reach "
                         f"{2 * reach:.2f} m; the deck levers its own fixing out")
    check_char("cantilever reach", reach, 0.5, 4.0)
    tx, ty = (b[0] - a[0]) / run, (b[1] - a[1]) / run
    nx, ny = ty, -tx                                    # right-hand plan normal
    m = into or Mesh()

    def P(s, u, zz):
        return (a[0] + tx * s + nx * u, a[1] + ty * s + ny * u, zz)

    z_j = z - deck_t                                    # joist tops carry the deck
    for k in range(joists):
        s = run * (k + 0.5) / joists
        _g.prism(m, [P(s - joist_w / 2, -backspan, 0)[:2], P(s + joist_w / 2, -backspan, 0)[:2],
                     P(s + joist_w / 2, reach, 0)[:2], P(s - joist_w / 2, reach, 0)[:2]],
                 z_j - joist_h, z_j, mat, cap_top=True, cap_bot=True)
        if brace_every and k % brace_every == 0:
            # knee brace: wall foot up to the joist soffit near the tip
            foot = P(s, 0.0, z_j - joist_h - brace_drop)
            head = P(s, reach * 0.78, z_j - joist_h)
            _g.sweep_section(m, [foot, head],
                             [(-joist_w * 0.45, -joist_w * 0.45), (joist_w * 0.45, -joist_w * 0.45),
                              (joist_w * 0.45, joist_w * 0.45), (-joist_w * 0.45, joist_w * 0.45)],
                             mat=mat, cap=True)
    # deck planks: one prism, the plank run is texture not geometry (pixeltex.py)
    _g.prism(m, [P(0, -backspan, 0)[:2], P(run, -backspan, 0)[:2],
                 P(run, reach + nose, 0)[:2], P(0, reach + nose, 0)[:2]],
             z_j, z, deck_mat, cap_top=True, cap_bot=True)
    # fascia beam closes the tip, so the deck edge is not a paper arris
    _g.prism(m, [P(0, reach, 0)[:2], P(run, reach, 0)[:2],
                 P(run, reach + nose, 0)[:2], P(0, reach + nose, 0)[:2]],
             z_j - fascia_h, z_j, mat, cap_top=True, cap_bot=True)
    if support_h > 0:
        _g.prism(m, [P(0, -backspan, 0)[:2], P(run, -backspan, 0)[:2],
                     P(run, 0, 0)[:2], P(0, 0, 0)[:2]],
                 z_j - joist_h - support_h, z_j - joist_h, "stone",
                 cap_top=True, cap_bot=True)
    return m


# ---------------------------------------------------------------------------
# 6. catenary
# ---------------------------------------------------------------------------
def catenary(a=None, b=None, sag=None, segs=14, radius=0.035, sides=5,
             pendants=6, pendant_w=0.30, pendant_h=0.38, pendant_t=0.02,
             mat="rope", pendant_mat="cloth", into=None):
    """A HANGING LINE: rope rail, bunting, festoon, chain. Nothing in the current
    pipeline sags, and docs/THE-PICTURE.md L5 lists overhead lines "sagging in real
    catenaries" as the thing that ties two sides of a street together across the void.

    sag       metres of droop at mid-span. Defaults to 9% of span; gated to 4-20%,
              which is the band _geom.sag_curve records for a rope actually strung.
              A parabola, not a true catenary: at that sag the two differ by well
              under a pixel at Octopath framing.
    pendants  triangular flags hung off the line. Bunting is one of the four named
              uses, and a bare 70 mm rope is invisible on a contact sheet.
    """
    a = (0.0, 0.0, 2.1 * CHAR) if a is None else a
    b = (7.0, 0.0, 2.1 * CHAR) if b is None else b
    span = math.dist(a[:2], b[:2])
    if span < 1e-6:
        raise SolidError("catenary: endpoints coincide")
    sag = 0.09 * span if sag is None else sag
    r = sag / span
    if not (SAG_RATIO[0] <= r <= SAG_RATIO[1]):
        raise SolidError(f"catenary sag {sag:.2f} m over {span:.2f} m span = {r:.1%}, "
                         f"outside the {SAG_RATIO[0]:.0%}-{SAG_RATIO[1]:.0%} band a "
                         f"strung line runs at")
    path = _g.sag_curve(a, b, sag, segs)
    sect = [(radius * math.cos(2 * math.pi * i / sides),
             radius * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    m = into or Mesh()
    _g.sweep_section(m, path, sect, mat=mat, cap=True)
    for k in range(pendants):
        t = (k + 0.5) / pendants
        i = min(len(path) - 1, int(round(t * (len(path) - 1))))
        px, py, pz = path[i]
        dx, dy = (b[0] - a[0]) / span, (b[1] - a[1]) / span
        hx, hy = -dy * pendant_t / 2, dx * pendant_t / 2
        for s in (-1, 1):
            m.tri((px - dx * pendant_w / 2 + hx * s, py - dy * pendant_w / 2 + hy * s, pz),
                  (px + dx * pendant_w / 2 + hx * s, py + dy * pendant_w / 2 + hy * s, pz),
                  (px + hx * s, py + hy * s, pz - pendant_h), pendant_mat)
        for (q0, q1) in (((-pendant_w / 2, 0.0), (pendant_w / 2, 0.0)),
                         ((pendant_w / 2, 0.0), (0.0, -pendant_h)),
                         ((0.0, -pendant_h), (-pendant_w / 2, 0.0))):
            m.quad((px + dx * q0[0] + hx, py + dy * q0[0] + hy, pz + q0[1]),
                   (px + dx * q1[0] + hx, py + dy * q1[0] + hy, pz + q1[1]),
                   (px + dx * q1[0] - hx, py + dy * q1[0] - hy, pz + q1[1]),
                   (px + dx * q0[0] - hx, py + dy * q0[0] - hy, pz + q0[1]), pendant_mat)
    return m


# ---------------------------------------------------------------------------
# 7. shelf_stack
# ---------------------------------------------------------------------------
def _kinked_run(length=11.0, kinks=(0.32, 0.68), amp=1.1, cut=0.9):
    """The default cliff plan. MEASURED law (STATE.md section 4): Octopath retaining and
    rock plans are curved or kinked, never straight runs, and every plan turn is a 45
    canted return, never a raw 90. Kinks at named fractions and a chamfer - deliberately
    NOT _geom.wobble, because L2's corollary is that raw random offsets are the failure,
    not the fix."""
    pts = [(0.0, -length / 2)]
    for i, f in enumerate(kinks):
        pts.append((amp * (1 if i % 2 == 0 else -1), -length / 2 + length * f))
    pts.append((0.0, length / 2))
    return _g.chamfer_corners(pts, cut=cut, min_turn_deg=25.0)


def shelf_stack(face=None, n=6, shelf_h=0.70 * CHAR, recess=0.62, lip_out=0.40,
                lip_h=0.30, undercut=0.34, back=2.2, mat="rock", into=None):
    """A cliff of stacked shelves with OVERHANGING DRIP LIPS - the measured Octopath
    scenery-cliff form (EL-9, "layered sandstone shelf stack with overhanging drip lips").

    Each shelf's face leans OUT as it rises off an undercut toe and then throws a lip
    past that face, so every shelf contributes one horizontal down-facing soffit. n
    shelves therefore give n undersides, and the whole silhouette is negative-draft.

    n         5-7. MEASURED. Anything outside that is not this form.
    shelf_h   0.6-0.8 CHAR. MEASURED. Gated through _geom.check_char.
    face      plan polyline of the cliff foot. Defaults to a kinked, chamfered run.
    """
    if not (SHELF_N[0] <= n <= SHELF_N[1]):
        raise SolidError(f"shelf_stack n={n} outside the measured {SHELF_N[0]}-{SHELF_N[1]} "
                         f"shelves of EL-9")
    check_char("shelf_h", shelf_h, *SHELF_H_CHAR)
    path = _kinked_run() if face is None else [tuple(p) for p in face]
    m = into or Mesh()
    for k in range(n):
        u = -recess * k                                  # each shelf steps back
        sect = [(u - back, 0.0),
                (u - undercut, 0.0),                     # undercut toe
                (u, shelf_h - lip_h),                    # face leans OUT as it rises
                (u + lip_out, shelf_h - lip_h),          # drip-lip soffit, faces DOWN
                (u + lip_out, shelf_h),                  # lip fascia
                (u - back, shelf_h)]
        base = [(p[0], p[1], k * shelf_h) for p in path]
        _g.sweep_section(m, base, sect, mat=mat, cap=True)
    return m


# ---------------------------------------------------------------------------
# 8. undercroft
# ---------------------------------------------------------------------------
def undercroft(span=14.0, bays=4, depth=4.4, pier_w=0.95, clear_h=1.35 * CHAR,
               head="round", deck_t=0.40, oversail=0.22, mat="stone",
               reveal_mat="reveal", into=None):
    """An ARCADED SPACE BENEATH A WALKABLE SURFACE, open at the sides, so the thing
    above is legibly HELD UP.

    docs/THE-PICTURE.md: "arcaded undercrofts beneath a causeway" is one of the
    undersides an extruded footprint has none of. Built the way masonry is: one solid
    block, then the bays are SUBTRACTED through the short axis, so the piers and the
    barrel soffits are the residue rather than parts placed next to each other. The
    deck oversails, which leaves a second down-facing ring at the eaves.

    bay clear span 1.0-4.0 CHAR and pier 0.25-1.0 CHAR are structural sanity limits,
    not measured off the reference set.
    """
    _need_bpy("undercroft")
    if bays < 2:
        raise SolidError("undercroft: an arcade needs at least 2 bays")
    check_char("pier_w", pier_w, 0.25, 1.0)
    bay = (span - (bays + 1) * pier_w) / bays
    if bay <= 0:
        raise SolidError(f"undercroft: {bays} bays and {bays + 1} piers of {pier_w} m "
                         f"do not fit in {span} m")
    check_char("bay clear span", bay, 1.0, 4.0)
    rise = {"round": 0.50, "segmental": 0.26, "pointed": 0.72}.get(head, 0.5) * bay
    H = clear_h + rise
    block = Mesh()
    _g.prism(block, _g.ensure_ccw(_rect(span, depth)), 0.0, H, mat,
             cap_top=True, cap_bot=True)
    tools = Mesh()
    for k in range(bays):
        cx = -span / 2 + pier_w * (k + 1) + bay * (k + 0.5)
        op = Opening(kind="arch", span=bay, height=H, head=head, rise=rise,
                     mat=reveal_mat, origin=(cx, 0.0, 0.0))
        tools.extend(op.tool(depth * 3.0))
    out = carve(block, tools, tool_mat=reveal_mat)
    deck = Mesh()
    _g.prism(deck, _g.ensure_ccw(_rect(span + 2 * oversail, depth + 2 * oversail)),
             H, H + deck_t, mat, cap_top=True, cap_bot=True)
    out.extend(deck)
    if into is not None:
        into.extend(out)
    return out


# ---------------------------------------------------------------------------
# 9. two_level
# ---------------------------------------------------------------------------
def two_level(region=None, z0=0.0, z1=None, corridor_w=2.0 * CHAR, deck_t=0.55,
              base_t=0.6, head="segmental", mat="stone", reveal_mat="reveal",
              into=None):
    """TWO WALKABLE SURFACES OVER ONE XY, with the upper one's underside visible.

    docs/THE-PICTURE.md section 6 item 4: a heightfield has exactly one walkable Z per
    XY, so Sunshade Catacombs routing one corridor under another is not merely harder to
    build, it is UNREPRESENTABLE. Built as a solid block whose top face is the upper
    route and through which the lower route is bored, so the tunnel soffit is the
    ceiling of one corridor and the floor slab of the other, from one piece of geometry.

    Headroom under the deck is gated at >= 1.2 CHAR. A structural rule, not measured.
    """
    _need_bpy("two_level")
    poly = _g.ensure_ccw(_rect(16.0, 11.0) if region is None else list(region))
    z1 = z0 + 2 * LEVEL if z1 is None else z1
    head_room = (z1 - deck_t) - z0
    if head_room < HEADROOM_CHAR * CHAR:
        raise SolidError(f"two_level: {head_room:.2f} m under the deck is "
                         f"{head_room / CHAR:.2f} CHAR, below the {HEADROOM_CHAR} CHAR "
                         f"a walkable corridor needs")
    block = Mesh()
    _g.prism(block, poly, z0 - base_t, z1, mat, cap_top=True, cap_bot=True)
    lo, hi = block.bbox()
    op = Opening(kind="tunnel", span=corridor_w, height=head_room, head=head,
                 mat=reveal_mat, bearing_deg=90.0, origin=(0.0, 0.0, z0))
    out = pierce(block, op, depth=2.5 * (hi[0] - lo[0]))
    if into is not None:
        into.extend(out)
    return out


# ---------------------------------------------------------------------------
# the ten, at defaults, for the contact sheet and the self-test
# ---------------------------------------------------------------------------
def _demo_carve(into=None):
    """A street cut out of a block. The tool's two ends and its top are EXACTLY coplanar
    with the block's, which is the case the Float solver breaks on."""
    block = Mesh()
    _g.prism(block, _g.ensure_ccw(_rect(18.0, 12.0)), 0.0, 3 * LEVEL, "stone",
             cap_top=True, cap_bot=True)
    street = Mesh()
    _g.box(street, -9.0, -2.25, LEVEL, 9.0, 2.25, 3 * LEVEL, "reveal")
    out = carve(block, street, tool_mat="reveal")
    if into is not None:
        into.extend(out)
    return out


def _demo_pierce(into=None):
    wall = Mesh()
    _g.prism(wall, _g.ensure_ccw(_rect(9.0, 1.0)), 0.0, 3 * LEVEL, "stone",
             cap_top=True, cap_bot=True)
    return pierce(wall, Opening("arch"), into=into)


def _demo_overhang(into=None):
    return overhang(into=into)


def _demo_batter(into=None):
    return batter(into=into)


def _demo_cantilever(into=None):
    """Anchor run along +X, so the projection lands on -Y and the joist soffits face the
    contact-sheet camera. The op's own default runs along +Y, which is the kit's authoring
    convention; at that bearing the sheet camera sees the top of the deck and none of the
    undersides the operation exists for."""
    return cantilever(anchor=((-3.4, 0.0, 2.0 * CHAR), (3.4, 0.0, 2.0 * CHAR)), into=into)


def _demo_undercroft(into=None):
    return undercroft(into=into)


def _demo_catenary(into=None):
    return catenary(into=into)


def _demo_shelf_stack(into=None):
    return shelf_stack(into=into)


def _demo_two_level(into=None):
    return two_level(into=into)


def _demo_fuse(into=None):
    """Two overlapping masses welded into one shell, so the result can be carved."""
    a = Mesh()
    _g.prism(a, _g.ensure_ccw(_rect(6.0, 4.0, -1.2, 0.0)), 0.0, 2 * LEVEL, "stone",
             cap_top=True, cap_bot=True)
    b = Mesh()
    _g.prism(b, _g.ensure_ccw(_rect(4.0, 6.0, 1.4, 0.6)), 0.0, 3 * LEVEL, "stone",
             cap_top=True, cap_bot=True)
    return fuse(a, b, into=into)


ELEMENTS = [
    ("carve", _demo_carve),
    ("pierce", _demo_pierce),
    ("overhang", _demo_overhang),
    ("batter", _demo_batter),
    ("cantilever", _demo_cantilever),
    ("undercroft", _demo_undercroft),
    ("catenary", _demo_catenary),
    ("shelf_stack", _demo_shelf_stack),
    ("two_level", _demo_two_level),
    ("fuse", _demo_fuse),
]


# ---------------------------------------------------------------------------
# self-test
#
# A generic "did it build" check plus ONE op-specific assert per operation, because
# generic checks are what let five weeks of green gates sit on dead output. Each
# op-specific assert measures the property the operation exists to deliver: a hole you
# can pass a ray through, a down-facing face above the base, a sag below the chord, two
# up-facing surfaces over one XY.
# ---------------------------------------------------------------------------
def _generic(name, m):
    ok, problems = _g.validate(m)
    assert ok, f"{name}: {problems}"
    assert m.dropped == 0, f"{name}: {m.dropped} faces dropped by the face guard"
    assert m.tris > 0, f"{name}: no geometry"
    lo, hi = m.bbox()
    for ax, k in enumerate("xyz"):
        assert hi[ax] - lo[ax] > 1e-3, f"{name}: flat in {k}, extent {hi[ax] - lo[ax]:.2e}"
    assert not any(c != c or abs(c) > 1e6 for p in m.v for c in p), f"{name}: runaway vertex"
    return lo, hi


def _specific(name, m):
    """Returns the one-line evidence string printed next to the op."""
    lo, hi = m.bbox()
    if name == "carve":
        thru = ray_crossings(m, (-14.0, 0.0, 2 * LEVEL), (1, 0, 0))
        solid = ray_crossings(m, (-14.0, 5.0, LEVEL * 0.5), (1, 0, 0))
        assert thru == 0, f"carve: street not cut through, {thru} crossings"
        assert solid == 2, f"carve: block no longer solid beside the street, {solid} crossings"
        v = volume(m)
        want = 18.0 * 12.0 * 3 * LEVEL - 18.0 * 4.5 * 2 * LEVEL
        assert abs(v - want) < 0.5, f"carve: volume {v:.1f} m3, expected {want:.1f}"
        return f"street: 0 crossings along it, 2 beside it, volume {v:.1f} m3 = block - slot"
    if name == "pierce":
        op = Opening("arch")
        c, ax = op.centre(), op.axis()
        o = (c[0] - ax[0] * 6, c[1] - ax[1] * 6, c[2])
        thru = ray_crossings(m, o, ax)
        solid = ray_crossings(m, (-4.2, -6.0, LEVEL), (0, 1, 0))
        rev = sum(1 for mt in m.m if mt == "reveal")
        assert thru == 0, f"pierce: not see-through, {thru} crossings"
        assert solid == 2, f"pierce: wall not solid beside the arch, {solid} crossings"
        assert rev >= 4, f"pierce: only {rev} reveal faces; jambs/soffit/cill not tagged"
        return f"0 crossings through the arch, 2 through the wall, {rev} reveal faces"
    if name == "overhang":
        u = undersides(m, lo[2] + 0.05)
        base = [p for p in m.v if p[2] < lo[2] + 1e-6]
        w0 = max(p[0] for p in base) - min(p[0] for p in base)
        assert len(u) >= 2, f"overhang: {len(u)} soffit faces above the base, want >= 2"
        assert hi[0] - lo[0] > w0 + 1e-6, "overhang: top no wider than the base"
        return (f"{len(u)} down-facing soffit faces above the base, plan grows "
                f"{w0:.2f} -> {hi[0]-lo[0]:.2f} m over {int(round((hi[2]-lo[2])/LEVEL))} levels")
    if name == "batter":
        top = [p for p in m.v if p[2] > hi[2] - 1e-6]
        w_top = max(p[0] for p in top) - min(p[0] for p in top)
        want = 4.2 - 2 * math.tan(math.radians(6.0)) * 2 * LEVEL
        assert abs(w_top - want) < 0.02, f"batter: top width {w_top:.3f} m, expected {want:.3f}"
        return f"top sets back to {w_top:.2f} m from 4.20 m over {2*LEVEL:.2f} m = 6.0 deg on every face"
    if name == "cantilever":
        u = undersides(m, lo[2] + 0.05)
        tip_up = ray_crossings(m, (0.0, 0.0, lo[2] - 1.0), (0, 0, 1))
        assert len(u) >= 8, f"cantilever: {len(u)} undersides, want the joist soffits"
        assert hi[1] - 1e-6 > 2.6, "cantilever: deck does not reach past the support"
        return f"{len(u)} down-facing faces above the base (joists + deck soffit + fascia)"
    if name == "undercroft":
        bays, pw, sp = 4, 0.95, 14.0
        bay = (sp - (bays + 1) * pw) / bays
        for k in range(bays):
            cx = -sp / 2 + pw * (k + 1) + bay * (k + 0.5)
            t = ray_crossings(m, (cx, -9.0, 1.0), (0, 1, 0))
            assert t == 0, f"undercroft: bay {k} blocked, {t} crossings"
        piers = [ray_crossings(m, (-sp / 2 + pw * (k + 0.5) + bay * k, -9.0, 1.0), (0, 1, 0))
                 for k in range(bays + 1)]
        assert all(p >= 2 for p in piers), f"undercroft: a pier is not solid, {piers}"
        u = undersides(m, lo[2] + 0.05)
        return (f"{bays}/{bays} bays of {bay:.2f} m see straight through, all {bays+1} piers "
                f"solid, {len(u)} down-facing soffit faces")
    if name == "catenary":
        span, chord, want = 7.0, 2.1 * CHAR, 0.09 * 7.0
        # Two corrections the obvious version gets wrong: the pendants hang BELOW the
        # line so the bbox is not the sag, and the rope is a swept tube so its lowest
        # SURFACE sits a section-radius under its centreline. Measuring mid-span against
        # the ends cancels the section exactly and needs no knowledge of it.
        rope = [m.v[i] for f, mt in zip(m.f, m.m) if mt == "rope" for i in f]
        end = min(p[2] for p in rope if p[0] < 0.35)
        mid = min(p[2] for p in rope if abs(p[0] - span / 2) < 0.35)
        drop = end - mid
        assert abs(drop - want) < 0.01, f"catenary: line sags {drop:.3f} m, wanted {want:.3f}"
        return (f"line sags {drop:.3f} m over a {span:.1f} m span = {drop/span:.1%}, "
                f"pendants reach {chord - lo[2]:.2f} m below the chord")
    if name == "shelf_stack":
        n, sh = 6, 0.70 * CHAR
        u = undersides(m, lo[2] + 0.05)
        area = sum(_g._area(p) for p in u)
        # one shelf's lip is a run of quads, not one face, so count the SHELVES the
        # soffit quads land on rather than the quads
        levels = {round((min(p[2] for p in q) - lo[2]) / sh) for q in u}
        assert len(levels) >= n, f"shelf_stack: soffits on {len(levels)} of {n} shelves"
        return (f"drip-lip soffits on {len(levels)}/{n} shelves, {len(u)} quads, "
                f"{area:.1f} m2 of overhanging underside")
    if name == "two_level":
        zs = up_surfaces_at(m, 0.0, 0.0)
        assert len(zs) >= 2, f"two_level: {len(zs)} walkable surfaces over (0,0), want 2"
        gap = zs[-1] - zs[0]
        assert gap > HEADROOM_CHAR * CHAR, f"two_level: only {gap:.2f} m between surfaces"
        thru = ray_crossings(m, (-22.0, 0.0, 0.6), (1, 0, 0))
        assert thru == 0, f"two_level: lower corridor blocked, {thru} crossings"
        return (f"up-facing surfaces over (0,0) at z={[round(z,2) for z in zs]}, "
                f"{gap:.2f} m apart, lower corridor clear")
    if name == "fuse":
        assert ray_crossings(m, (-20.0, 0.0, LEVEL), (1, 0, 0)) == 2, \
            "fuse: not one shell"
        return f"one welded shell, volume {volume(m):.1f} m3"
    return ""


def _main():
    print(f"{'operation':14s} {'tris':>6s} {'faces':>6s}  {'bbox w x d x h (m)':>22s}  evidence")
    print("-" * 118)
    fails = []
    for name, fn in ELEMENTS:
        try:
            m = fn()
            lo, hi = _generic(name, m)
            ev = _specific(name, m)
        except AssertionError as e:
            fails.append(str(e))
            print(f"{name:14s} {'FAIL':>6s}")
            continue
        except (SolidError, _g.ScaleError) as e:
            fails.append(f"{name}: {type(e).__name__}: {e}")
            print(f"{name:14s} {'ERROR':>6s}  {e}")
            continue
        size = f"{hi[0]-lo[0]:6.2f}{hi[1]-lo[1]:8.2f}{hi[2]-lo[2]:8.2f}"
        print(f"{name:14s} {m.tris:6d} {len(m.f):6d}  {size:>22s}  {ev}")
    print()
    if fails:
        print("PROBLEMS")
        for x in fails:
            print("  " + x)
        return 1
    print(f"all {len(ELEMENTS)} operations build, are non-degenerate, and each one's own "
          f"property is measured above")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
