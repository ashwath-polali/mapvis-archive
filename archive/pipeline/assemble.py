"""MAPVIS ASSEMBLE — place modular pieces by SOCKET MATCHING, not by looking at anything.

This is the part Ash named as the actual hard problem: "you can find assets, but the hard part is
also piecing them together to make a map, especially with ai's shitty eyes and screwed perception."

He is right that placement by perception is dead. But modular kits are not placed by perception.
Verified on disk: KayKit floors are exactly 2.00 x 2.00 m and 4.00 x 4.00 m, and KayKit walls are
exactly 2.00 m wide. Those are SOCKETS. A wall does not go "where it looks good" — it goes on the
boundary between a walkable cell and a non-walkable one, facing out, because that is the only place
a wall can go. A corner piece goes where two such boundaries meet. A stair goes where two levels
touch and traffic must cross.

So assembly here is a GRID WALK plus a lookup table. Every placement is derived from the cell's
neighbourhood, exactly like an autotile bitmask in 2D. No model looks at anything. Run it twice and
you get identical output.

What it does NOT solve: the grid itself. Socket matching gives locally-correct, globally-aimless —
WFC's documented failure. It makes a legal town, not necessarily a good one. That limit is real and
is stated here so nobody claims otherwise later.

Usage:
    blender -b -P mapvis/assemble.py -- <grid.json> [--out=FILE] [--view=iso|game|plan]

<grid.json> is the octoscore/p0 shape: { w, h, lift: (num|null)[], walk: num[] }
"""
import json
import math
import os
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "mapwright", "modules"))
try:
    import mw_look
except ImportError:
    mw_look = None

bpy.ops.wm.read_factory_settings(use_empty=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
pos = [a for a in ARGS if not a.startswith("--")]


def opt(f, d=None):
    for a in ARGS:
        if a.startswith(f + "="):
            return a.split("=", 1)[1]
    return d


CELL = 2.0                     # the verified KayKit module
STOREY = 2.0                   # one level of lift, in metres
KAY = os.path.join(HERE, "assets", "kits",
                   "kaykit-dungeon-remastered", "KayKit_Dungeon_Pack_1.1_FREE", "Assets", "fbx")

# the catalogue. Every entry is a piece whose footprint is one CELL, so it snaps by construction.
PIECES = {
    "floor":        "floor_dirt_small_A.fbx",
    "floor_b":      "floor_dirt_small_B.fbx",
    "floor_c":      "floor_dirt_small_C.fbx",
    "floor_weeds":  "floor_dirt_small_weeds.fbx",
    "wall":         "wall.fbx",
    "wall_arched":  "wall_arched.fbx",
    "wall_window":  "wall_archedwindow_open.fbx",
    "wall_corner":  "wall_corner.fbx",
    "wall_broken":  "wall_broken.fbx",
    "stairs":       "stairs.fbx",
    "stairs_walled": "stairs_walled.fbx",
    "column":       "column.fbx",
    "pillar":       "pillar_decorated.fbx",
    "foundation":   "floor_foundation_allsides.fbx",
    "found_corner": "floor_foundation_corner.fbx",
}

_cache = {}


def piece(key):
    """import once, then instance. Linked duplicates keep 10,000 placements cheap."""
    if key in _cache:
        return _cache[key]
    path = os.path.join(KAY, PIECES[key])
    if not os.path.isfile(path):
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        return None
    src = new[0]
    for o in new[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    src.hide_render = True
    src.location = (0, 0, -9999)
    _cache[key] = src.data
    return src.data


def place(key, x, y, z, rot_z=0.0):
    me = piece(key)
    if me is None:
        return None
    ob = bpy.data.objects.new(f"{key}", me)
    bpy.context.collection.objects.link(ob)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, rot_z)
    return ob


# ---------------------------------------------------------------------------
def main():
    if not pos:
        sys.exit(__doc__)
    g = json.load(open(pos[0], encoding="utf-8"))
    W, H = g["w"], g["h"]
    walk = g["walk"]
    lift = g.get("lift") or [0] * (W * H)

    def wk(x, y):
        return 0 <= x < W and 0 <= y < H and walk[y * W + x]

    def lv(x, y):
        v = lift[y * W + x] if wk(x, y) else None
        return 0 if v is None else int(round(v / 16.0)) if v > 8 else int(v)

    def wx(x):
        return (x - W / 2.0) * CELL

    def wy(y):
        return (H / 2.0 - y) * CELL

    n_floor = n_wall = n_corner = n_stair = 0
    # deterministic floor variation: a hash of the cell, never a random number
    variants = ["floor", "floor_b", "floor_c", "floor_weeds"]

    for y in range(H):
        for x in range(W):
            if not wk(x, y):
                continue
            L = lv(x, y)
            z = L * STOREY
            h = (x * 73856093) ^ (y * 19349663)
            place(variants[(h >> 4) % len(variants)], wx(x), wy(y), z)
            n_floor += 1

            # WALLS: on every edge where a walkable cell meets a non-walkable one at this level.
            # There is no judgement here — a wall can only go on a boundary.
            #   -Y edge -> rot 0, +X edge -> rot 90, +Y edge -> rot 180, -X edge -> rot 270
            nb = [(0, -1, 0.0), (1, 0, math.pi / 2), (0, 1, math.pi), (-1, 0, -math.pi / 2)]
            open_sides = []
            for dx, dy, rot in nb:
                if wk(x + dx, y + dy) and lv(x + dx, y + dy) == L:
                    continue
                open_sides.append((dx, dy, rot))

            # a cell open on exactly two ADJACENT sides is a corner: use the corner piece once
            if len(open_sides) == 2:
                (ax, ay, ar), (bx, by, br) = open_sides
                if ax * bx + ay * by == 0:          # perpendicular
                    place("wall_corner", wx(x), wy(y), z, ar)
                    n_corner += 1
                    open_sides = []

            for i, (dx, dy, rot) in enumerate(open_sides):
                # deterministic variety: mostly plain wall, occasional window or arch, so the run
                # is not one repeated mesh. Chosen by cell hash, not by anyone's taste.
                hh = ((x * 2654435761) ^ (y * 2246822519) ^ (i * 668265263)) & 0xFFFF
                key = "wall"
                if hh % 11 == 0:
                    key = "wall_window"
                elif hh % 17 == 0:
                    key = "wall_arched"
                elif hh % 23 == 0:
                    key = "wall_broken"
                place(key, wx(x), wy(y), z, rot)
                n_wall += 1

            # STAIRS: where a walkable neighbour sits exactly one level below, facing the drop
            for dx, dy, rot in nb:
                if wk(x + dx, y + dy) and lv(x + dx, y + dy) == L - 1:
                    place("stairs_walled", wx(x + dx), wy(y + dy), (L - 1) * STOREY, rot)
                    n_stair += 1
                    break

    print(f"ASSEMBLE: {n_floor} floors, {n_wall} walls, {n_corner} corners, {n_stair} stairs "
          f"= {n_floor + n_wall + n_corner + n_stair} placements, all socket-derived")

    # one clay material over everything, so this is judged as GEOMETRY
    clay = bpy.data.materials.new("clay")
    clay.use_nodes = True
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.60, 0.60, 0.59, 1)
    b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    for me in bpy.data.meshes:
        me.materials.clear()
        me.materials.append(clay)

    # --- camera ---
    VIEW = opt("--view", "game")
    RES = int(opt("--res", "2600"))
    OUT = opt("--out", os.path.join(HERE, "assemble.png"))
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.clip_start = 0.1
    cam.data.clip_end = 100000
    sc.camera = cam
    if VIEW == "plan":
        fwd, right, up = (mathutils.Vector((0, 0, -1)), mathutils.Vector((1, 0, 0)),
                          mathutils.Vector((0, 1, 0)))
    else:
        el = math.radians(30.0 if VIEW == "iso" else 24.0)
        az = math.radians(45.0 if VIEW == "iso" else 20.0)
        d = mathutils.Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el),
                              math.sin(el)))
        fwd = (-d).normalized()
        right = fwd.cross(mathutils.Vector((0, 0, 1))).normalized()
        up = right.cross(fwd).normalized()
    corners = [mathutils.Vector((wx(cx), wy(cy), cz))
               for cx in (0, W) for cy in (0, H) for cz in (0, 6)]
    look = sum(corners, mathutils.Vector()) / len(corners)
    u = [(p - look).dot(right) for p in corners]
    v = [(p - look).dot(up) for p in corners]
    su, sv = max(u) - min(u), max(v) - min(v)
    sc.render.resolution_x = RES
    sc.render.resolution_y = max(2, int(RES * sv / su))
    cam.data.ortho_scale = su * 1.02
    c = look + right * ((max(u) + min(u)) / 2) + up * ((max(v) + min(v)) / 2)
    cam.location = c - fwd * 5000
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    if mw_look:
        mw_look.apply_render(sc, transparent=False)
        mw_look.apply_light(sc, {"sun": {"azimuth": 310, "elevation": 33, "color": "#ffffff"}})
        sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.32
    sc.render.film_transparent = False
    sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
    print(f"ASSEMBLE OK -> {OUT}")


main()
