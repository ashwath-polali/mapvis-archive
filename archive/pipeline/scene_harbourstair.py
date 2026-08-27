"""
scene_harbourstair.py - ONE scene, built to the theory, at Octopath screen scale.

Organising idea, five words: A WATER STAIR THROUGH A SEAWALL.

Everything in frame either serves that or hides part of it. This is not a town and not a
terrain reconstruction; it is one room built around one piece of civil engineering, which
is what docs/THE-PICTURE.md says an Octopath map actually is.

  L1 ordered reveal   the arch hides the upper terrace until you are through it
  L2 co-visible cause EVERY deviation is now a record in ops_cause, not a hardcoded
                      coordinate and not a hash of a seed. Two of them:
                        seawall_bay#4 sets back 1.70 m because outcrop_east is in its
                        line, and the outcrop stands in the setback where you can see it
                        mooring_post#1 stands 3.00 m west of its 6 m beat because the
                        slipway notch is cut through its station
                      Six undeviated siblings of each module exist. How many are LEGIBLE
                      in a given frame is the thing R2 actually measures, and the measured
                      answer on the axis route is 4 on approach and 2 at the stair foot -
                      so this scene fails R2 in close frames. See the audit output, not
                      this docstring.
  L3 scale referent   treads, a door, a rail, bollards silhouetted against every big mass
  L4 asym enclosure   closed left/back by mass, ONE open arc to seaward
  edge operator       no flat cap anywhere: coping, balustrade, raked coping
  light               one cold key + hand-placed warm points, most of the frame dark
  contact             nothing meets anything without something in the joint

The seawall is built as SEVEN BAYS rather than one swept run, and that is not cosmetic.
R2 counts undeviated siblings in the object-id buffer, so if a wall is one mesh it has no
bays and a kinked wall can never show three straight bays beside the kink. The base module
has to be an addressable object or the law cannot be measured.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P scene_harbourstair.py
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'kit'))

import circulation as C          # noqa: E402
import masses as M               # noqa: E402
import ops_cause as OC           # noqa: E402
import retaining as R            # noqa: E402
import thresholds as T           # noqa: E402
import water_terrain as W        # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


SCENE = 'scene_harbourstair'

CHAR = 1.7
LEVEL = 1.7                      # EL-2: one level is exactly one CHAR
WATER = 0.0
QUAY = 1.2                       # quay deck sits just above the water
TERR = QUAY + LEVEL * 2          # the terrace the stair climbs to

WALL_Y = 7.0                     # the NOMINAL seawall line - the base module's station
# quay_wall sweeps its section SEAWARD of the path, so the path line IS the wall's
# landward face and the terrace has to start on it. Measured off the built mesh:
# seawall_bay_3 spans y 4.16 to 7.00 for a path at 7.00. The previous version started the
# terrace 1.6 m behind the path and left a 1.6 x 3.1 m open slot the length of the wall,
# which leaked into R4's open arcs and into the visible-volume series R1 reads.
BAY = 6.5                        # one seawall bay
N_BAYS = 7
BAY_X0 = -N_BAYS * BAY / 2.0     # -22.75

POST_BEAT = 6.0                  # the mooring bollard module: one every 6 m
POST_Y = -5.6
N_POSTS = 7

# The two causes, as geometry, before anything is built. A cause is a thing in the world
# with a size, not a note in a solver: that is the entire content of L2.
OUTCROP = (6.5, 6.5, WATER + 1.6)        # centre, astride the nominal wall line
OUTCROP_R = (3.2, 1.9, 2.4)              # rx, ry, rz
SLIPWAY_X = -12.0                        # the boat notch cut through the quay front
SLIPWAY_W = 4.4

PARTS = []
REG = OC.Registry(SCENE)


def put(mat, mesh, x=0.0, y=0.0, z=0.0, rot=0.0, name=None):
    if mesh is None:
        return
    v, f = mesh
    if not v or not f:
        return
    c, s = math.cos(rot), math.sin(rot)
    PARTS.append((mat, [(x + p[0] * c - p[1] * s, y + p[0] * s + p[1] * c, z + p[2])
                        for p in v], [tuple(q) for q in f], name))


def box(mat, x0, y0, z0, x1, y1, z1, name=None):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    PARTS.append((mat, v, f, name))


def poly(mat, pts, z0, z1, cap=True, name=None):
    n = len(pts)
    v = [(p[0], p[1], z0) for p in pts] + [(p[0], p[1], z1) for p in pts]
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if cap:
        f.append(tuple(range(n, 2 * n)))
    PARTS.append((mat, v, f, name))


def rock(mat, cx, cy, cz, rx, ry, rz, lobes=7, name=None):
    """An irregular boulder, closed-form.

    Was a hash of a seed nudging every vertex. Two harmonics now, so this is the SAME
    boulder at every size: a rock that differs from its neighbours has to earn it through
    a recorded cause rather than by drawing a different number.
    """
    v, f = [], []
    rings = 5
    for i in range(rings):
        t = (i + 0.5) / rings
        zz = cz + rz * math.cos(t * math.pi)
        rr = math.sin(t * math.pi)
        for j in range(lobes):
            a = 2 * math.pi * j / lobes
            k = 1.0 + 0.17 * math.cos(2 * a) + 0.09 * math.cos(3 * a + 1.05)
            v.append((cx + rx * rr * k * math.cos(a),
                      cy + ry * rr * k * math.sin(a), zz))
    for i in range(rings - 1):
        for j in range(lobes):
            a = i * lobes + j
            b = i * lobes + (j + 1) % lobes
            f.append((a, b, b + lobes, a + lobes))
    PARTS.append((mat, v, f, name))


def tuft(mat, x, y, z, h=0.24, w=0.13, lean_x=0.0, lean_y=1.0, blades=3):
    """A weed clump: three crossed cards, the cheapest thing that breaks a razor seam.

    The lean was a hash of a seed. It is now a direction the caller supplies, because a
    weed in a joint leans OUT of the joint - away from the mass it is growing against and
    toward the light. That is a cause a viewer already knows, which is the whole test.
    """
    v, f = [], []
    L = math.hypot(lean_x, lean_y) or 1.0
    lx, ly = lean_x / L * 0.16, lean_y / L * 0.16
    for b in range(blades):
        a = math.pi * b / blades
        dx, dy = math.cos(a) * w, math.sin(a) * w
        o = len(v)
        v += [(x - dx, y - dy, z), (x + dx, y + dy, z),
              (x + dx * 0.35 + lx, y + dy * 0.35 + ly, z + h),
              (x - dx * 0.35 + lx, y - dy * 0.35 + ly, z + h)]
        f += [(o, o + 1, o + 2, o + 3)]
    PARTS.append((mat, v, f, None))


def seam(mat, a, b, z, spacing=0.9, h=0.22, period=2, route_x=0.0, sweep_w=2.8,
         lean_x=0.0, lean_y=1.0):
    """Weeds along a built-to-ground seam: on a beat, and DELETED along the walked line.

    The old version chose which stations got a tuft, how far each sat off the line and how
    tall it was from a hash of `seed`. That is noise used AS the mask, which is the one
    thing L9 forbids outright. Now the mask is a field the viewer can compute for
    themselves: distance from the route axis. Swept bare where feet fall, taller further
    out. `period` is the beat, so the run is periodic and reads as growth rather than as
    scatter.
    """
    ux, uy = b[0] - a[0], b[1] - a[1]
    run = math.hypot(ux, uy)
    if run < 1e-6:
        return
    ux, uy = ux / run, uy / run
    for i in range(int(run / spacing)):
        if i % period:
            continue
        t = (i + 0.5) * spacing
        x, y = a[0] + ux * t, a[1] + uy * t
        clear = abs(x - route_x) - sweep_w / 2.0
        if clear <= 0.0:
            continue                                  # swept: the path reads as used
        tuft(mat, x, y, z, h=h * min(1.0, 0.45 + 0.55 * clear / 2.4),
             lean_x=lean_x, lean_y=lean_y)


# ------------------------------------------------------------------ the scene

def bay_span(i):
    return BAY_X0 + i * BAY, BAY_X0 + (i + 1) * BAY


def build():
    del PARTS[:]
    REG.__init__(SCENE)

    # --- L4: closed left and back, ONE open arc to seaward (-Y). Water plane.
    box('water', -70, -70, WATER - 3.0, 70, 6.0, WATER)

    # --- THE CAUSES, registered before anything can lean on them. Both are real
    # geometry with their own object in the id buffer; a cause the buffer cannot see is a
    # reason in a solver, and 379 of those were rejected on sight.
    outcrop = REG.cause('outcrop_east', 'outcrop', OUTCROP,
                        radius=max(OUTCROP_R), obj='outcrop_east',
                        note='resistant head standing in the nominal seawall line')
    rock('rock', OUTCROP[0], OUTCROP[1], OUTCROP[2], *OUTCROP_R, name='outcrop_east')
    rock('rock', OUTCROP[0] + 2.6, OUTCROP[1] + 1.5, OUTCROP[2] + 0.7,
         2.0, 1.5, 1.7, name='outcrop_east')

    slipway = REG.cause('slipway_notch', 'boundary', (SLIPWAY_X, -6.4, QUAY),
                        radius=SLIPWAY_W / 2 + 0.4, obj='water_steps',
                        note='boat landing cut through the quay front')

    # --- THE SEAWALL, seven bays on one nominal line. Bay 4 is the only one that moves,
    # and what moves it is the outcrop standing in its way: the setback is COMPUTED from
    # the cause's own landward face plus a clearance, so the number in the record and the
    # number in the geometry cannot drift apart.
    setback = (OUTCROP[1] + OUTCROP_R[1] + 0.30) - WALL_Y
    wall_y = []
    for i in range(N_BAYS):
        x0, x1 = bay_span(i)
        el = REG.element('seawall_bay', ((x0 + x1) / 2, WALL_Y, QUAY),
                         obj=f'seawall_bay_{i}')
        if x0 < OUTCROP[0] + OUTCROP_R[0] and x1 > OUTCROP[0] - OUTCROP_R[0]:
            REG.deviate(el, outcrop, 'offset', (0.0, setback))
        wall_y.append(el.pos[1])
        put('ashlar', R.quay_wall(path=[(x0, el.pos[1]), (x1, el.pos[1])],
                                  h_above_water=TERR - WATER),
            name=f'seawall_bay_{i}')

    # --- the QUAY at water level: the space you arrive in. It follows the wall, so where
    # the wall stands back the deck comes forward into the setback.
    poly('flag', [(BAY_X0, -6.5), (-BAY_X0, -6.5), (-BAY_X0, WALL_Y), (BAY_X0, WALL_Y)],
         WATER, QUAY)
    for i in range(N_BAYS):
        if wall_y[i] > WALL_Y:
            x0, x1 = bay_span(i)
            box('flag', x0, WALL_Y, WATER, x1, wall_y[i], QUAY)
    put('ashlar', R.quay_wall(path=[(BAY_X0, -6.5), (-BAY_X0, -6.5)],
                              h_above_water=QUAY - WATER + 1.4), name='quay_edge')

    # --- the MOORING BOLLARDS: one every 6 m, which is the module. The post whose station
    # the slipway is cut through stands clear of it on the west cheek, and the slipway is
    # 3 m away in the same shot.
    put('ashlar', W.quay_steps_water(width_m=SLIPWAY_W, z_deck_m=QUAY, z_water_m=WATER),
        SLIPWAY_X, -6.4, name='water_steps')
    for i in range(N_POSTS):
        x = -(N_POSTS - 1) / 2 * POST_BEAT + i * POST_BEAT
        el = REG.element('mooring_post', (x, POST_Y, QUAY), obj=f'mooring_post_{i}')
        if abs(x - SLIPWAY_X) < SLIPWAY_W / 2:
            REG.deviate(el, slipway, 'offset', (-3.0, 0.0))
        put('ashlar', W.mooring_post(z_deck_m=QUAY, z_water_m=WATER),
            el.pos[0], el.pos[1], name=f'mooring_post_{i}')

    # --- THE HERO: the water stair driven through the seawall on the axis.
    # Two flights with a landing, because 3.4 m cannot be one flight (EL-3).
    put('step', C.flight_with_landing(rise_m=LEVEL * 2, width_m=1.8,
                                      landing_len_m=1.8, riser_m=0.2125),
        0.0, 1.6, QUAY)
    # the cheek follows the flight, so its run is fixed by the flight's own
    # riser/going - it cannot rake at its own angle
    for s in (-1, 1):
        put('ashlar', C.cheek_wall(rise_m=LEVEL * 2, run_m=LEVEL * 2 / 0.21 * 0.45),
            s * 1.28, 1.6, QUAY)

    # --- THE THRESHOLD: an arch through the wall on the axis, in an UNDEVIATED bay. It
    # hides the upper terrace until you are through it - that is the reveal (L1), and it
    # is the one hole you can see through.
    axis_bay = N_BAYS // 2
    put('ashlar', T.round_arch_postern(span=2.6, spring_h=2.4, wall_t=1.5,
                                       wall_h=TERR + 1.1, invert_z=0.0),
        0.0, wall_y[axis_bay] + 0.8, TERR - 0.02)

    # --- the UPPER TERRACE, revealed through the arch. Per bay, so it notches back with
    # the wall instead of hanging out in front of it.
    for i in range(N_BAYS):
        x0, x1 = bay_span(i)
        box('flag', x0, wall_y[i], TERR - 0.3, x1, 26.0, TERR)
    # edge operator: NO flat cap anywhere. Balustrade on the drop, broken by the arch
    # mouth so the opening reads.
    for i in range(N_BAYS):
        x0, x1 = bay_span(i)
        y = wall_y[i] - 0.15
        for a, b in ((x0, min(x1, -2.2)), (max(x0, 2.2), x1)):
            if b - a > 0.6:
                put('coping', R.stone_balustrade(path=[(a, y), (b, y)]), 0, 0, TERR)

    # --- the BACKDROP mass: a party-wall row closing the top of the frame (L4),
    # tall and narrow, four storeys, with its own base course and cornice.
    put('plaster', M.mass_row_terrace(unit_w_m=5.2, unit_count=7, depth_m=9.0,
                                      storeys=4, floor_to_floor_m=3.2),
        0.0, 19.5, TERR)
    # L3: doors and windows are the known-size referents on that big mass
    for i in range(7):
        x = -15.6 + i * 5.2
        put('timber', T.arched_doorway(base_z=0.0), x, 14.9, TERR)
        for s in (1, 2, 3):
            put('timber', T.window_opening(cill_z=1.0, base_z=0.0),
                x, 14.9, TERR + s * 3.2)

    # --- a lower outbuilding on the quay, breaking the wall's long run and
    # giving the foreground something to occlude with
    put('plaster', M.mass_box_house(width_m=5.6, depth_m=5.0, eaves_h_m=5.4,
                                    storeys=2, floor_to_floor_m=2.7),
        -20.0, 2.4, QUAY)
    put('tile', M.roof_gable_prism(span_m=5.0, length_m=5.6, pitch_deg=48.0),
        -20.0, 2.4, QUAY + 5.4, math.pi / 2)
    put('timber', T.arched_doorway(base_z=0.0), -20.0, -0.2, QUAY)

    # --- CONTACT LAYER. Nothing meets anything without something in the joint.
    contact(wall_y)

    # --- FOREGROUND OCCLUDER: a real object inches from the lens, defocused.
    rock('rock', -13.0, -13.5, WATER + 0.6, 4.6, 3.0, 3.4, name='reef_head')


def contact(wall_y):
    # weeds where the quay deck meets the seawall foot, per bay, leaning out of the joint
    for i in range(N_BAYS):
        x0, x1 = bay_span(i)
        seam('moss', (x0 + 0.2, wall_y[i] - 0.15), (x1 - 0.2, wall_y[i] - 0.15), QUAY,
             lean_y=-1.0)
    # and along the terrace foot behind the balustrade
    for i in range(N_BAYS):
        x0, x1 = bay_span(i)
        y = wall_y[i] + 0.05
        seam('moss', (x0 + 0.3, y), (x1 - 0.3, y), TERR, h=0.18, period=3, lean_y=1.0)
    # a three-band algae stain at the waterline, as geometry so it catches light
    for dz, inset in ((0.02, 0.00), (0.16, 0.03), (0.30, 0.06)):
        poly('algae', [(BAY_X0 + inset, -6.5 + inset), (-BAY_X0 - inset, -6.5 + inset),
                       (-BAY_X0 - inset, -6.42 + inset), (BAY_X0 + inset, -6.42 + inset)],
             WATER + dz, WATER + dz + 0.09, cap=True)
    # drift piled against the outbuilding's footing
    seam('moss', (-22.9, -0.15), (-17.1, -0.15), QUAY, spacing=0.6, h=0.2, period=1,
         lean_y=-1.0)


def emit_registry():
    """Write the registry beside the geometry. frameaudit reads this file, so it is
    written on every build and can never be stale relative to what was just built."""
    return REG.save(OC.registry_path(SCENE, HERE))


# ------------------------------------------------------------------ blender

MAT = {
    'water':   (0.020, 0.045, 0.062, 0.15),
    'ashlar':  (0.300, 0.290, 0.272, 0.85),
    'flag':    (0.250, 0.243, 0.230, 0.90),
    'step':    (0.330, 0.318, 0.298, 0.88),
    'coping':  (0.345, 0.335, 0.315, 0.85),
    'plaster': (0.400, 0.378, 0.340, 0.92),
    'timber':  (0.115, 0.082, 0.055, 0.90),
    'tile':    (0.180, 0.098, 0.070, 0.92),
    'rock':    (0.190, 0.183, 0.175, 0.95),
    'moss':    (0.055, 0.075, 0.038, 0.98),
    'algae':   (0.045, 0.062, 0.040, 0.55),
}


def _material(mat):
    m = bpy.data.materials.new(mat)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    r, g, bl, rough = MAT.get(mat, (0.3, 0.3, 0.3, 0.9))
    b.inputs['Base Color'].default_value = (r, g, bl, 1)
    b.inputs['Roughness'].default_value = rough
    if mat == 'water':
        b.inputs['Roughness'].default_value = 0.06
        if 'Metallic' in b.inputs:
            b.inputs['Metallic'].default_value = 0.4
    if 'Specular IOR Level' in b.inputs:
        b.inputs['Specular IOR Level'].default_value = 0.12
    return m


def _emit(objname, mat, parts):
    V, F = [], []
    for v, f in parts:
        o = len(V)
        V += list(v)
        F += [tuple(i + o for i in q) for q in f]
    me = bpy.data.meshes.new(objname)
    me.from_pydata(V, [], F)
    me.validate(verbose=False)
    ob = bpy.data.objects.new(objname, me)
    bpy.context.collection.objects.link(ob)
    bevel(ob, 0.012)                          # an arris on everything catches light
    ob.data.materials.append(_material(mat))
    return ob


def flush():
    """Registered elements and causes become their OWN objects; everything else merges by
    material. R2 reads object names out of the id buffer, so a registered thing that got
    merged into a material blob is a thing the audit cannot see."""
    out = []
    named, bulk = {}, {}
    for mat, v, f, name in PARTS:
        if name:
            named.setdefault((name, mat), []).append((v, f))
        else:
            bulk.setdefault(mat, []).append((v, f))
    for (name, mat), parts in named.items():
        out.append(_emit(name, mat, parts))
    for mat, parts in bulk.items():
        out.append(_emit(mat, mat, parts))
    return out


def bevel(ob, w):
    md = ob.modifiers.new('bev', 'BEVEL')
    md.width = w
    md.segments = 2
    md.limit_method = 'ANGLE'
    md.angle_limit = math.radians(35)


def warm_point(x, y, z, power=180.0, size=0.35):
    d = bpy.data.lights.new('pt', 'POINT')
    d.energy = power
    d.color = (1.0, 0.62, 0.30)
    d.shadow_soft_size = size
    o = bpy.data.objects.new('pt', d)
    bpy.context.collection.objects.link(o)
    o.location = Vector((x, y, z))


def setup():
    # ONE COLD WIDE KEY. Most of the frame is allowed to go near-black.
    w = bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    # 60-80% of the frame is ALLOWED to go near-black. That is the measured
    # condition and it is the single largest lever in the whole stack.
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.007, 0.013, 0.028, 1)
    w.node_tree.nodes['Background'].inputs[1].default_value = 1.0
    key = bpy.data.lights.new('key', 'SUN')
    key.energy = 0.5
    key.color = (0.46, 0.60, 1.0)
    key.angle = math.radians(6)
    ko = bpy.data.objects.new('key', key)
    bpy.context.collection.objects.link(ko)
    ko.rotation_euler = (math.radians(64), 0, math.radians(-56))

    # THREE TO EIGHT HAND-PLACED WARM POINTS. One is the hero, on the axis,
    # inside the arch - it is simultaneously the reward and the waypoint.
    warm_point(0.0, WALL_Y + 1.6, TERR + 1.5, 420, 0.5)          # hero, in the arch
    warm_point(-20.0, -0.6, QUAY + 2.6, 120)                     # outbuilding door
    warm_point(-2.4, 2.2, QUAY + 1.4, 90)                        # stair foot
    warm_point(12.0, 6.2, QUAY + 2.2, 110)                       # quay lamp
    for x in (-10.4, 0.0, 10.4):                                 # windows above
        warm_point(x, 14.6, TERR + 3.6, 70)

    cam_d = bpy.data.cameras.new('cam')
    cam_d.lens = float(arg('--lens', 55))
    cam_d.clip_start, cam_d.clip_end = 0.4, 600
    cam_d.dof.use_dof = True
    cam_d.dof.focus_distance = float(arg('--focus', 34))
    cam_d.dof.aperture_fstop = float(arg('--fstop', 1.6))
    cam = bpy.data.objects.new('cam', cam_d)
    bpy.context.collection.objects.link(cam)
    # Octopath's facades stay frontal, but the camera is offset ALONG the wall so
    # the composition is not a dead-centre elevation. Yaw stays 0; only X moves.
    pitch = math.radians(float(arg('--pitch', 19)))
    dist = float(arg('--dist', 46))
    off = float(arg('--offx', -3.0))
    tgt = Vector((off, 6.0, QUAY + 3.0))
    cam.location = tgt + Vector((0, -dist * math.cos(pitch), dist * math.sin(pitch)))
    cam.rotation_euler = (math.radians(90) - pitch, 0, 0)
    bpy.context.scene.camera = cam


def render(path):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    try:
        sc.eevee.taa_render_samples = 128
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
        sc.eevee.use_bloom = True
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build()
    objs = flush()
    tris = 0
    for o in objs:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    setup()
    reg = emit_registry()
    probs, notes = REG.structural_check()
    print(f'[scene] {len(objs)} objects, {tris} triangles')
    print(f'[cause] {len(REG.causes)} causes, {len(REG.elements)} elements, '
          f'{len(REG.deviations)} deviations -> {reg}')
    for n in notes:
        print('  ' + n)
    for p in probs:
        print('  PROBLEM ' + p)
    p = os.path.join(HERE, 'shots', 'scene-harbourstair.png')
    render(p)
    print('->', p)
