"""SETPIECE — one harbour edge, every layer present, no shortcuts. The honest test.

Not a map. Not a layout system. One small assembly, built to find out whether the eight-layer
stack produces architecture when it is actually applied, because it never has been. Every previous
artifact in this project was layer 1 (badly) plus layer 4 (as boxes) — two of eight, and the two
that carry the least.

What is here:
    L1 ground      quay at water level, terrace one storey up, both as discrete planes
    L2 retaining   the seawall that holds the terrace: footing, coursed battered face,
                   string course, oversailing coping, buttresses, and a parapet on its crown
    L3 circulation a grand stair from quay to terrace with a landing and raking cheek walls
    L4 masses      buildings with base course, string course, oversailing eaves, pitched roofs
    L5 threshold   an arched gate driven through the seawall, recessed, with real voussoirs
    L6 frame       water below, ground rising behind the terrace
    L7 light       one key, deep shadow, cool ambient (mw_look)
    L8 life        deliberately absent - standing law, stages render empty

Untextured grey. If the structure does not read here, it does not read, and no art rescues it.

    blender -b -P mapvis/setpiece_harbour.py -- [--out=FILE] [--view=iso|game|plan] [--res=2600]
"""
import math
import os
import sys

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "mapwright", "modules"))
import kit  # noqa: E402
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


VIEW = opt("--view", "game")
RES = int(opt("--res", "2600"))
OUT = opt("--out", os.path.join(HERE, "setpiece.png"))

# ---------------------------------------------------------------------------
# the assembly, in metres. A person is 1.7 m tall; check every number against that.
# ---------------------------------------------------------------------------
SEA = -0.35
QUAY_Z = 0.0
TERR_Z = 4.6           # one storey up: 2.7 character heights, the Octopath "storey"
X0, X1 = -34.0, 34.0   # the run of the seawall
QUAY_Y0 = -15.0        # seaward edge of the quay
WALL_Y = 0.0           # the seawall sits here
TERR_Y1 = 26.0         # the terrace runs back to here

M_STONE, M_TRIM, M_DARK, M_ROOF, M_GROUND = 0, 1, 2, 3, 4

mesh = kit.Mesh()

# --- L1: the two ground planes ---------------------------------------------
kit.slab(mesh, X0 - 6, X1 + 6, QUAY_Y0, WALL_Y, QUAY_Z, M_GROUND, drop_to=SEA - 1.4)
kit.slab(mesh, X0 - 6, X1 + 6, WALL_Y, TERR_Y1, TERR_Z, M_GROUND)

# --- L5: the gate, and the wall built AROUND it -----------------------------
# the opening is a fact the wall has to accommodate, which is why the wall is built in two runs
GATE_CX, GATE_W, GATE_H = 9.0, 4.2, 3.5
WALL_DEPTH = 2.2

# --- L2: the seawall, in two runs flanking the gate, plus its parapet --------
kit.retaining_wall(mesh, X0, GATE_CX - GATE_W / 2 - 0.6, WALL_Y, QUAY_Z, TERR_Z,
                   M_STONE, M_TRIM, face=-1)
kit.retaining_wall(mesh, GATE_CX + GATE_W / 2 + 0.6, X1, WALL_Y, QUAY_Z, TERR_Z,
                   M_STONE, M_TRIM, face=-1)
# the span over the gate head
kit.retaining_wall(mesh, GATE_CX - GATE_W / 2 - 0.6, GATE_CX + GATE_W / 2 + 0.6, WALL_Y,
                   QUAY_Z + GATE_H + 0.5, TERR_Z, M_STONE, M_TRIM, face=-1,
                   buttresses=False, string=False)
kit.arch_gate(mesh, GATE_CX, WALL_Y - WALL_DEPTH / 2 + 0.1, QUAY_Z, GATE_W, GATE_H,
              WALL_DEPTH, M_STONE, M_TRIM, M_DARK)

# parapet on the terrace side of the wall crown, broken where the stair lands
STAIR_CX, STAIR_W = -13.0, 7.0
kit.parapet(mesh, X0, STAIR_CX - STAIR_W / 2 - kit.CHEEK_W, WALL_Y + 0.4, TERR_Z, M_STONE, M_TRIM)
kit.parapet(mesh, STAIR_CX + STAIR_W / 2 + kit.CHEEK_W, X1, WALL_Y + 0.4, TERR_Z, M_STONE, M_TRIM)

# --- L3: the grand stair, quay up to terrace --------------------------------
kit.grand_stair(mesh, STAIR_CX, QUAY_Y0 + 3.0, QUAY_Z, TERR_Z, STAIR_W, M_STONE, M_TRIM)

# --- L4: masses on the terrace ----------------------------------------------
# Rule, not composition: nothing freestanding. Buildings sit in a continuous ROW with shared party
# walls, backing onto the hill behind, which is how a terrace town is actually built. Gable ends
# alternate so the roofline is not one long ridge.
row_y = 11.4
x = X0 - 3.0
i = 0
while x < X1 - 4.0:
    w = 8.5 + 3.0 * ((i * 7) % 3)          # deterministic width variation, no randomness
    d = 8.0 + 1.6 * ((i * 5) % 2)
    h = 6.0 + 1.5 * ((i * 3) % 3)
    kit.building_mass(mesh, x + w / 2, row_y + d / 2 - 4.0, TERR_Z, w, d, h,
                      M_STONE, M_TRIM, M_ROOF, ridge_along_x=(i % 3 != 1))
    x += w                                  # party walls: no gap between neighbours
    i += 1

# the tower: braced into the wall run at the east end, the one thing that breaks the roofline
kit.building_mass(mesh, X1 - 5.0, 3.4, TERR_Z, 6.8, 6.8, 14.5, M_STONE, M_TRIM, M_ROOF,
                  pitch=0.95, ridge_along_x=False)

# --- L6: the frame - water, and the hill the town backs onto -----------------
mesh.quad((X0 - 14, QUAY_Y0 - 26, SEA), (X1 + 14, QUAY_Y0 - 26, SEA),
          (X1 + 14, QUAY_Y0, SEA), (X0 - 14, QUAY_Y0, SEA), M_DARK)
# stepped ground rising behind, built as SOLID mass: each terrace has a retaining face and closed
# sides, so it reads as a hill the town is cut into rather than as floating shelves
hy = TERR_Y1
hz = TERR_Z
for i in range(6):
    nz = hz + 2.6
    kit.retaining_wall(mesh, X0 - 6, X1 + 6, hy, hz, nz, M_STONE, M_TRIM,
                       face=-1, buttresses=False, string=False)
    kit.slab(mesh, X0 - 6, X1 + 6, hy, hy + 4.2, nz, M_GROUND)
    for sx_ in (X0 - 6, X1 + 6):           # close the sides
        mesh.quad((sx_, hy, nz), (sx_, hy + 4.2, nz),
                  (sx_, hy + 4.2, TERR_Z), (sx_, hy, TERR_Z), M_STONE)
    hy += 4.2
    hz = nz

# close the ends of the whole assembly so it is a solid body, not a card
for sx_ in (X0 - 6, X1 + 6):
    mesh.quad((sx_, QUAY_Y0, QUAY_Z), (sx_, TERR_Y1, QUAY_Z),
              (sx_, TERR_Y1, TERR_Z), (sx_, QUAY_Y0, TERR_Z), M_STONE)
    mesh.quad((sx_, QUAY_Y0, SEA - 1.4), (sx_, WALL_Y, SEA - 1.4),
              (sx_, WALL_Y, QUAY_Z), (sx_, QUAY_Y0, QUAY_Z), M_STONE)

# frame the SETPIECE, not the whole scene: the camera target is the wall and what it holds
FRAME = [(X0 - 8, QUAY_Y0 - 2, SEA), (X1 + 8, QUAY_Y0 - 2, SEA),
         (X0 - 8, TERR_Y1 + 6, TERR_Z + 16), (X1 + 8, TERR_Y1 + 6, TERR_Z + 16)]

# ---------------------------------------------------------------------------
me = bpy.data.meshes.new("setpiece")
me.from_pydata(mesh.v, [], mesh.f)
me.update()
ob = bpy.data.objects.new("setpiece", me)
bpy.context.collection.objects.link(ob)

# ground is DARKER than the built stone. In every Octopath frame the paving reads well
# below the walls; equal values are why earlier renders had no figure/ground separation.
for name, val in (("stone", 0.62), ("trim", 0.72), ("dark", 0.05),
                  ("roof", 0.44), ("ground", 0.30)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (val, val, val * 0.985, 1)
    b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    ob.data.materials.append(m)
for i, p in enumerate(me.polygons):
    p.material_index = mesh.m[i]

# --- camera ----------------------------------------------------------------
scene = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.clip_start = 0.1
cam.data.clip_end = 100000.0
scene.camera = cam

if VIEW == "plan":
    fwd, right, up = (mathutils.Vector((0, 0, -1)), mathutils.Vector((1, 0, 0)),
                      mathutils.Vector((0, 1, 0)))
else:
    el = math.radians(30.0 if VIEW == "iso" else 24.0)
    az = math.radians(45.0 if VIEW == "iso" else 12.0)
    d = mathutils.Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el),
                          math.sin(el)))
    fwd = (-d).normalized()
    right = fwd.cross(mathutils.Vector((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()

pts = [mathutils.Vector(v) for v in FRAME]
look = sum(pts, mathutils.Vector()) / len(pts)
u = [(p - look).dot(right) for p in pts]
v = [(p - look).dot(up) for p in pts]
su, sv = max(u) - min(u), max(v) - min(v)
scene.render.resolution_x = RES
scene.render.resolution_y = max(2, int(RES * sv / su))
cam.data.ortho_scale = su * 1.03
c = look + right * ((max(u) + min(u)) / 2) + up * ((max(v) + min(v)) / 2)
cam.location = c - fwd * 3000
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()

if mw_look:
    mw_look.apply_render(scene, transparent=False)
    mw_look.apply_light(scene, {"sun": {"azimuth": 152, "elevation": 21, "color": "#ffffff"}})
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.05
else:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.film_transparent = False
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print(f"SETPIECE OK: {len(mesh.f)} faces, {VIEW} view -> {OUT}")
