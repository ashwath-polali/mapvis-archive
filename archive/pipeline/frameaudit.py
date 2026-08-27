"""
frameaudit.py - the instrument. Measures the RELATIONAL laws, per frame, along a route.

Why this file exists, and why it is the first thing that had to be built:

Every metric this project has ever used is a statistic over the SET of elements -
density, walkable fraction, luminance percentiles, face counts, size ladders.
All of them are permutation-invariant: shuffle every element's position and the
number does not move. Measured, not argued - pixel-shuffling a reference frame
left Otsu separability at 0.863 before and 0.863 after.

Beauty in built space is carried by ORDER (what you saw before this, what is
revealed next) and RELATION (which mass occludes which, whether the cause of a
deviation is visible in the same frame as the deviation). Neither is a property
of the set, so no set-statistic can see either. That is why five weeks of green
gates coincided with five weeks of rejected output.

So this measures four things that are order- or relation-sensitive, all of them
computable from a frame's own depth and object-id buffers, none of them asking
any model whether a picture is pretty:

  R1  ORDERED REVEAL       visible-volume series along the route: 2-5 reveal
                           events, running max non-decreasing, global max in the
                           final fifth, and the mass revealed there is unique
  R2  CO-VISIBLE CAUSE     a deviating element's causing geometry must project
                           into the SAME frustum, with >=3 undeviated siblings
  R3  ANCHORED SCALE       every mass over 4 CHAR of silhouette must have a
                           known-size element silhouetted against it
  R4  ASYMMETRIC ENCLOSURE closed over most azimuths, open over 1-2 arcs

R2 read NOT MEASURED until ops_cause.py existed, because nothing in the builder
recorded WHY anything deviated and the theory names co-visibility of cause and
effect as THE mechanism. It is now read off the registry the scene writes beside
its geometry: for every deviation, is its cause in this frustum, and are three
undeviated siblings of the same module in it too. The buffer is the same one R3
uses, so there is one raycaster and one source of truth.

It reports per frame and it fails loudly. An instrument that never fails is
broken, not the map.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P frameaudit.py -- --scene scene_harbourstair --route 0,-14,0,20
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

import ops_cause as OC  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


CHAR = 1.7
EYE = 1.55                       # camera height above the walk surface
RES = int(arg('--res', 320))     # audit renders are small; this is measurement
N_FRAMES = int(arg('--frames', 9))

# elements whose real size a player already knows - the scale vocabulary (R3).
# Matched as SUBSTRINGS of the object name, because registered elements now carry their
# own names (mooring_post_3, water_steps) instead of being merged into a material blob,
# and L3's vocabulary lists a rail or post at 0.6 CHAR as a referent in its own right.
SCALE_TAGS = ('step', 'coping', 'timber', 'moss', 'post')


def is_scale_referent(name):
    return any(t in name for t in SCALE_TAGS)


# ------------------------------------------------------------------ buffers

def setup_passes():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x = RES
    sc.render.resolution_y = int(RES * 9 / 16)
    sc.render.resolution_percentage = 100
    sc.render.use_compositing = False
    sc.render.use_sequencer = False
    vl = bpy.context.view_layer
    vl.use_pass_z = True
    vl.use_pass_object_index = True
    try:
        sc.eevee.taa_render_samples = 1
    except Exception:
        pass
    for i, ob in enumerate(bpy.context.scene.objects):
        if ob.type == 'MESH':
            ob.pass_index = i + 1


def frustum_ids(scene, eye, fwd, hfov=math.radians(52), nx=96, aspect=16 / 9):
    """A depth + object-name buffer by RAYCAST rather than by render.

    Blender will not hand back Z or IndexOB pixels in background mode without a
    compositor file round-trip, and that round-trip returned an empty image. Rays
    give the same two buffers exactly, with no render, no EXR and no guessing
    which EXR channel holds the integer ids."""
    base = fwd.normalized()
    right = base.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(base).normalized()
    ny = max(4, int(nx / aspect))
    dep = bpy.context.evaluated_depsgraph_get()
    depth = np.full((ny, nx), np.inf, np.float32)
    names = np.empty((ny, nx), dtype=object)
    names[:] = ''
    th = math.tan(hfov / 2)
    tv = th / aspect
    for j in range(ny):
        sy = (1.0 - 2.0 * (j + 0.5) / ny) * tv
        for i in range(nx):
            sx = (2.0 * (i + 0.5) / nx - 1.0) * th
            ray = (base + right * sx + up * sy).normalized()
            hit, loc, nor, idx, obj, mw = scene.ray_cast(dep, eye, ray, distance=400.0)
            if hit:
                depth[j, i] = (loc - eye).length
                names[j, i] = obj.name if obj else ''
    return depth, names


# ------------------------------------------------------------------ raycast

def visible_volume(scene, origin, forward, fov=math.radians(50), rays=17):
    """Approximate the visible volume from a point by casting a fan and summing
    hit distance^2. Order-sensitive by construction: this is the series R1 reads."""
    total = 0.0
    dep = bpy.context.evaluated_depsgraph_get()
    for i in range(rays):
        for j in range(rays):
            ax = (i / (rays - 1) - 0.5) * fov
            ay = (j / (rays - 1) - 0.5) * fov * 0.56
            d = forward.copy()
            d.rotate(Vector((0, 0, 1)).to_track_quat('Z', 'Y').to_euler())
            dv = Vector((math.sin(ax), math.cos(ax), math.tan(ay))).normalized()
            # rotate dv into the forward frame
            base = forward.normalized()
            right = base.cross(Vector((0, 0, 1))).normalized()
            up = right.cross(base).normalized()
            ray = (base * dv.y + right * dv.x + up * dv.z).normalized()
            hit, loc, nor, idx, obj, mw = scene.ray_cast(dep, origin, ray, distance=300.0)
            r = (loc - origin).length if hit else 300.0
            total += min(r, 300.0) ** 2
    return total / (rays * rays)


def enclosure(scene, origin, azimuths=36, frame_top=math.radians(28)):
    """R4. Cast a ring of rays; an azimuth is OPEN if nothing rises above the
    frame-top angle along it. Report the contiguous open arcs."""
    dep = bpy.context.evaluated_depsgraph_get()
    openness = []
    for a in range(azimuths):
        th = 2 * math.pi * a / azimuths
        best = -math.pi / 2
        for elev in (0.03, 0.12, 0.25, 0.40, 0.58):
            d = Vector((math.cos(th), math.sin(th), math.tan(elev))).normalized()
            hit, loc, nor, idx, obj, mw = scene.ray_cast(dep, origin, d, distance=200.0)
            if hit:
                dist = math.hypot(loc.x - origin.x, loc.y - origin.y)
                if dist > 0.2:
                    best = max(best, math.atan2(loc.z - origin.z, dist))
        openness.append(best < frame_top)
    arcs, run = [], 0
    for i in range(azimuths * 2):
        if openness[i % azimuths]:
            run += 1
        else:
            if run:
                arcs.append(run)
            run = 0
        if i == azimuths - 1 and run == 0:
            pass
    if run:
        arcs.append(run)
    arcs = [a for a in arcs if a <= azimuths]
    span = [a * 360.0 / azimuths for a in arcs]
    return openness, span


def masses_in_frame(depth, names):
    """R3. Silhouette share per object, and whether each LARGE mass has a
    known-size element silhouetted right against it. A mass with no scale
    referent has no size, only extent - which is literally what "topographic
    model" means."""
    H, W = depth.shape
    total = H * W
    uniq = {}
    for n in np.unique(names):
        if not n:
            continue
        uniq[str(n)] = int((names == n).sum())
    big = {n: a for n, a in uniq.items() if a / total > 0.02}
    anchored = {}
    for n in big:
        m = (names == n)
        halo = m.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
            halo |= np.roll(np.roll(m, dy, 0), dx, 1)
        touch = {str(t) for t in np.unique(names[halo & ~m]) if t}
        anchored[n] = any(is_scale_referent(t) for t in touch)
    sky = float((~np.isfinite(depth)).mean())
    return {'areas': uniq, 'big': big, 'anchored': anchored, 'sky': sky}


# ------------------------------------------------------------------ the audit

def audit(route, reg=None):
    scene = bpy.context.scene
    if scene.camera is None:
        cd = bpy.data.cameras.new('auditcam')
        c = bpy.data.objects.new('auditcam', cd)
        scene.collection.objects.link(c)
        scene.camera = c
    obj_by_index = {ob.pass_index: ob.name for ob in scene.objects if ob.type == 'MESH'}

    pts = []
    for i in range(N_FRAMES):
        t = i / max(1, N_FRAMES - 1)
        seg = t * (len(route) - 1)
        k = min(int(seg), len(route) - 2)
        f = seg - k
        a, b = route[k], route[k + 1]
        pts.append(Vector((a[0] + (b[0] - a[0]) * f,
                           a[1] + (b[1] - a[1]) * f,
                           a[2] + (b[2] - a[2]) * f)))

    rows = []
    for i, p in enumerate(pts):
        nxt = pts[min(i + 1, len(pts) - 1)]
        fwd = (nxt - p)
        if fwd.length < 1e-6:
            fwd = pts[i] - pts[max(0, i - 1)]
        fwd.z = 0
        if fwd.length < 1e-6:
            fwd = Vector((0, 1, 0))
        fwd.normalize()
        eye = p + Vector((0, 0, EYE))
        vv = visible_volume(scene, eye, fwd)
        openness, arcs = enclosure(scene, eye)
        # the place camera stands off behind the walk point and looks down 19 deg,
        # which is the measured Octopath framing, and audits THAT view
        pitch = math.radians(19)
        cam_eye = eye - fwd * 13.0 + Vector((0, 0, 4.4))
        look = (fwd * math.cos(pitch) - Vector((0, 0, math.sin(pitch)))).normalized()
        depth, names = frustum_ids(scene, cam_eye, look, nx=int(arg('--nx', 96)))
        mf = masses_in_frame(depth, names)
        # R2 off the SAME buffer. One raycaster, one source of truth.
        r2 = reg.check_frame(names) if reg is not None else None
        rows.append({'i': i, 'p': [round(v, 2) for v in p],
                     'visvol': round(vv, 1), 'open_arcs': [round(a) for a in arcs],
                     'sky': round(mf['sky'], 3), 'masses': mf, 'r2': r2})

    return rows


def report(rows, reg=None, probs=()):
    vv = [r['visvol'] for r in rows]
    n = len(vv)
    print()
    print('=' * 78)
    print('FRAME AUDIT - relational laws, per frame along the route')
    print('=' * 78)
    print(f"{'#':>3} {'visible vol':>12} {'runmax':>8} {'open arcs deg':>16} "
          f"{'big masses':>11} {'anchored':>9} {'dev expl':>9}")
    runmax = -1.0
    mono = True
    for r in rows:
        runmax_prev = runmax
        runmax = max(runmax, r['visvol'])
        if runmax < runmax_prev - 1e-9:
            mono = False
        mf = r['masses'] or {}
        big = mf.get('big', {})
        anch = mf.get('anchored', {})
        na = sum(1 for k in big if anch.get(k))
        d = r.get('r2')
        cell = '-' if d is None else f"{d['passing']}/{d['present']}"
        print(f"{r['i']:>3} {r['visvol']:>12.1f} {runmax:>8.1f} "
              f"{str(r['open_arcs']):>16} {len(big):>11} {na:>9} {cell:>9}")

    # R1 ORDERED REVEAL
    reveals = sum(1 for i in range(1, n) if vv[i] > vv[i - 1] * 1.45)
    gmax_at = int(np.argmax(vv))
    r1 = (2 <= reveals <= 5) and mono and (gmax_at >= int(0.8 * (n - 1)))
    # R4 ASYMMETRIC ENCLOSURE
    r4_frames = sum(1 for r in rows if 1 <= len(r['open_arcs']) <= 2)
    r4 = r4_frames >= 0.6 * n
    # R3 ANCHORED SCALE
    tot_big = sum(len((r['masses'] or {}).get('big', {})) for r in rows)
    tot_anch = sum(sum(1 for k in (r['masses'] or {}).get('big', {})
                       if (r['masses'] or {}).get('anchored', {}).get(k))
                   for r in rows)
    r3 = tot_big > 0 and tot_anch / tot_big >= 0.8
    # R2 CO-VISIBLE CAUSE. A deviation whose own element is out of frame is not counted:
    # the law is that a deviation is explained WHERE IT IS SEEN, not everywhere.
    r2_present = sum(r['r2']['present'] for r in rows if r.get('r2'))
    r2_pass = sum(r['r2']['passing'] for r in rows if r.get('r2'))
    r2 = (reg is not None and not probs and r2_present > 0
          and r2_pass / r2_present >= 0.8)

    print()
    print(f"R1 ORDERED REVEAL        {'PASS' if r1 else 'FAIL'}   "
          f"reveal events {reveals} (want 2-5), running max "
          f"{'monotonic' if mono else 'DIPS'}, global max at frame {gmax_at}/{n-1} "
          f"(want final fifth)")
    print(f"R3 ANCHORED SCALE        {'PASS' if r3 else 'FAIL'}   "
          f"{tot_anch}/{tot_big} large masses have a known-size element against them "
          f"(want >=80%)")
    print(f"R4 ASYMMETRIC ENCLOSURE  {'PASS' if r4 else 'FAIL'}   "
          f"{r4_frames}/{n} frames closed with 1-2 open arcs (want >=60%)")
    if reg is None:
        print('R2 CO-VISIBLE CAUSE      NOT MEASURED - no cause registry beside this')
        print('                         scene. Until every deviating element carries the')
        print('                         id of the geometry that caused it, this cannot be')
        print('                         checked and must not be claimed.')
    else:
        print(f"R2 CO-VISIBLE CAUSE      {'PASS' if r2 else 'FAIL'}   "
              f"{r2_pass}/{r2_present} in-frame deviations have their cause in")
        print(f"{'':25}the same frame with {OC.SIBLINGS_REQUIRED} undeviated siblings "
              f"(want >=80%)")
        print(f"{'':25}{len(reg.deviations)} deviations over {len(reg.elements)} "
              f"elements, {len(reg.causes)} causes")
        for pr in probs:
            print(f"{'':25}STRUCTURAL {pr}")
        if not reg.deviations:
            print(f"{'':25}nothing deviates, so R2 is vacuous here, not satisfied")
    print('=' * 78)
    return {'R1': r1, 'R2': r2, 'R3': r3, 'R4': r4}


def load_spec(spec):
    """Build a COMPOSED spec through the normal assembler, so the audit measures
    the same geometry the pipeline actually produces - not a hand-built scene."""
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
    for mat, v, f in A.PARTS:
        B.emit(mat, v, f)
    B.flush()
    B.setup(geom['span_m'], False)
    tag = os.path.basename(os.path.dirname(spec)) or 'spec'
    rp = os.path.join(HERE, 'shots', f'causes-compose_{tag.replace("-", "_")}.json')
    return tag, (rp if os.path.exists(rp) else None)


if __name__ == '__main__':
    spec = arg('--spec')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    reg, probs, rp = None, [], None

    if spec:
        tag, rp = load_spec(os.path.abspath(spec))
    else:
        mod = arg('--scene', 'scene_harbourstair')
        tag = mod
        m = __import__(mod)
        m.build()
        m.flush()
        if hasattr(m, 'setup'):
            m.setup()
        if hasattr(m, 'emit_registry'):
            rp = m.emit_registry()

    # The registry is read back off DISK, so the audit sees exactly what was
    # exported and a broken round-trip fails loudly here instead of silently.
    if rp and os.path.exists(rp):
        reg = OC.Registry.load(rp)
        probs, notes = reg.structural_check()
        print(f'[cause] loaded {rp}')
        for x in notes:
            print('  ' + x)

    raw = arg('--route', '0,-14,1.2;0,3,1.2;0,9,4.6;0,20,4.6')
    route = [[float(v) for v in seg.split(',')] for seg in raw.split(';')]
    rows = audit(route, reg)
    verdict = report(rows, reg, probs)
    payload = {'route': route, 'spec': spec,
               'rows': [{k: v for k, v in r.items() if k != 'masses'} for r in rows],
               'verdict': verdict, 'r2_structural_problems': list(probs)}
    for out in (os.path.join(HERE, 'shots', f'audit-{tag}.json'),
                os.path.join(HERE, 'shots', 'audit-last.json')):
        json.dump(payload, open(out, 'w'), indent=1)
    print('->', os.path.join(HERE, 'shots', f'audit-{tag}.json'))
