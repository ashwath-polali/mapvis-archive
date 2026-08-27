"""
edges_ab.py - run ops_edges over an existing assembled map and render the pair.

Why a separate file: ops_edges.py has no Blender dependency and its self-test runs
under plain python, which is worth keeping. This is the Blender-side driver, and it
is the smallest thing that can produce an honest A/B.

The base geometry is built ONCE and is the same Blender objects in every render.
The section geometry is added as further objects and toggled with hide_render, so a
before/after pair differs by exactly that visibility flag - not by a rebuild, not by
a second run of the assembler, and not by a second camera. The camera transform is
printed and compared so the claim is checkable rather than asserted.

Two pairs come out. The far pair is the assembler's own town-wide shot, unchanged.
The near pair exists because that shot resolves 17 pixels per metre, so a 0.095 m
coping oversail lands on 1.6 pixels and the frame cannot report what the operator
did in either direction. The near station is not chosen: the target is the midpoint
of the longest raking run the operator found, and the standoff is the nearest of 420
distance/pitch/azimuth candidates that both clears a 12 CHAR frame-width floor and
has an unobstructed sightline by raycast.

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P edges_ab.py -- \
        --spec place/villefranche/spec --grey
"""
import math
import os
import sys

import bpy
from mathutils import Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, 'kit')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import assemble_map as A
import build_place as B
import ops_edges as E

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.join(_HERE, 'shots')

# candidate near stations, closest and lowest first. The first one with an
# unobstructed line to the target wins. The first version of this file hardcoded
# 45 m at 26 degrees and put the camera inside a building; a hill town has 27 m of
# terrain and 12.8 m masses, so where a close camera can stand is a raycast
# question and must not be a chosen number.
NEAR_DIST = (26.0, 34.0, 45.0, 60.0, 80.0, 105.0, 140.0)
NEAR_PITCH = (24.0, 32.0, 40.0, 50.0, 60.0)
NEAR_YAW = tuple(range(0, 360, 30))
MIN_FRAME_CHAR = 12.0


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


def tri_table(objs):
    per = {}
    for ob in objs:
        ob.data.calc_loop_triangles()
        per[ob.name] = per.get(ob.name, 0) + len(ob.data.loop_triangles)
    return per, sum(per.values())


def cam_state(cam):
    return (tuple(round(v, 6) for v in cam.location),
            tuple(round(v, 6) for v in cam.rotation_euler),
            round(cam.data.lens, 4))


def frame_w(cam, dist):
    """Metres of world across the frame at that standoff."""
    fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
    return 2 * dist * math.tan(fov / 2)


def px_per_m(cam, dist):
    """Ground sampling at the target, so the report can say whether the frame is
    even able to resolve a 0.1 m member."""
    return bpy.context.scene.render.resolution_x / frame_w(cam, dist)


def trim_samples(added, n=140):
    """A deterministic even sample of the section geometry's own vertices. These are
    the points the near frame has to show; nothing else about the near shot matters."""
    pts = [Vector(v.co) for ob in added for v in ob.data.vertices]
    if not pts:
        return []
    k = max(1, len(pts) // n)
    return pts[::k][:n]


def best_station(cam, tgt, samples):
    """The near station is SCORED, not chosen. A station is legal when its sightline
    to the target is unobstructed and the frame is at least MIN_FRAME_CHAR wide, and
    among the legal ones the winner is the one from which the most of the section
    geometry is actually visible.

    Three earlier criteria all produced a useless frame and each failure is the
    reason for a clause here: fixing the azimuth to the assembler's -y blocked all 35
    candidates; taking the nearest clear station returned 26 m, which frames 11 m of
    world and is a macro shot; and taking the first legal station returned a street
    canyon whose walls are openings, which carry no profile, so the before and after
    frames differed on 1.08% of pixels. Counting visible trim points is the only one
    of the four that measures the thing the frame is for.

    Visibility is a raycast from the station to each sample point, counted as visible
    when the first hit is within 0.15 m of it. No render, no image, no judgement.

    The score is the sum of 1/L^2 over the visible points, not their count. Counting
    them picked 140 m, the FARTHEST legal station, because a wider view sees more
    trim; 1/L^2 is proportional to the pixels each point occupies, so the score is
    the section geometry's screen footprint, which is what the frame is being asked
    to report.

    Returns (distance, pitch_deg, yaw_deg, location, visible, score, legal) or None.
    """
    dep = bpy.context.evaluated_depsgraph_get()
    sc = bpy.context.scene
    dists = [d for d in NEAR_DIST if frame_w(cam, d) >= MIN_FRAME_CHAR * 1.7]
    print(f'[ab] near candidates {NEAR_DIST} m -> {dists} m after the '
          f'{MIN_FRAME_CHAR} CHAR frame-width floor '
          f'({frame_w(cam, dists[0]):.1f} m wide at the nearest)')
    best, legal = None, 0
    for d in dists:
        for pdeg in NEAR_PITCH:
            p = math.radians(pdeg)
            for ydeg in NEAR_YAW:
                yw = math.radians(ydeg)
                off = Vector((math.sin(yw) * math.cos(p),
                              -math.cos(yw) * math.cos(p), math.sin(p))) * d
                loc = tgt + off
                ray = off.normalized()
                hit, _a, _n, _i, _o, _m = sc.ray_cast(dep, tgt + ray * 1.6, ray,
                                                      distance=d - 1.6)
                if hit:
                    continue
                up, _a, _n, _i, _o, _m = sc.ray_cast(dep, loc, Vector((0, 0, 1)),
                                                     distance=400.0)
                if up:
                    continue
                legal += 1
                seen, score = 0, 0.0
                for q in samples:
                    v = q - loc
                    L = v.length
                    if L < 1.0 or L > d * 2.2:
                        continue
                    h, at, _n, _i, _o, _m = sc.ray_cast(dep, loc, v / L, distance=L + 1)
                    if h and (at - q).length < 0.15:
                        seen += 1
                        score += 1.0 / (L * L)
                if best is None or score > best[5]:
                    best = (d, pdeg, ydeg, loc, seen, score)
    return None if best is None else best + (legal,)


def pair(tag, added, cam, dist):
    for ob in added:
        ob.hide_render = True
    B.render(os.path.join(OUT, f'edges-before{tag}.png'))
    a = cam_state(cam)
    for ob in added:
        ob.hide_render = False
    B.render(os.path.join(OUT, f'edges-after{tag}.png'))
    b = cam_state(cam)
    print(f'[ab] pair{tag or " (far)"}: camera identical {a == b}, '
          f'{px_per_m(cam, dist):.1f} px per metre at the target')
    return a == b


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    geom = A.main()
    parts = list(A.PARTS)
    print(f'[ab] assemble_map emitted {len(parts)} parts')

    for mat, v, f in parts:
        B.emit(mat, v, f)
    base = B.flush()
    per_base, tris_base = tri_table(base)

    new_parts, st = E.apply_to_parts(parts)
    B.BUCKETS.clear()
    for mat, v, f in new_parts:
        B.emit(mat, v, f)
    added = B.flush()
    for ob in added:
        ob.name = ob.name.split('.')[0] + '_trim'
    per_add, tris_add = tri_table(added)

    B.setup(geom['span_m'], B.TEXTURED)
    cam = bpy.context.scene.camera
    far_dist = float(arg('--dist', 260))
    ok_far = pair('', added, cam, far_dist)

    focus = st['focus'] or (geom['span_m'] * 0.5, geom['span_m'] * 0.5, 12.0)
    tgt = Vector(focus) + Vector((0, 0, 2.0))
    samples = trim_samples(added)
    stn = best_station(cam, tgt, samples)
    ok_near, near, seen = False, None, 0
    if stn is None:
        print('[ab] no legal near station found; near pair skipped')
    else:
        near, npitch, nyaw, cam.location, seen, score, legal = stn
        cam.rotation_euler = (math.radians(90 - npitch), 0, math.radians(nyaw))
        print(f'[ab] near station {near:.0f} m, pitch {npitch:.0f} deg, '
              f'yaw {nyaw:.0f} deg - best of {legal} legal stations out of '
              f'{len(NEAR_DIST) * len(NEAR_PITCH) * len(NEAR_YAW)}, showing '
              f'{seen}/{len(samples)} sampled trim points, '
              f'screen-footprint score {score:.4f}')
        ok_near = pair('-near', added, cam, near)

    print()
    print('=' * 72)
    print('EDGE OPERATOR - A/B over place/villefranche/spec')
    print('=' * 72)
    print(f'camera identical within each pair : far {ok_far}, near {ok_near}')
    print(f'near pair aimed at               : {focus} '
          f'(midpoint of the longest raking run found)')
    print(f'near standoff                    : '
          + (f'{near:.0f} m, scored by raycast, {seen}/{len(samples)} sampled '
             f'trim points visible' if near else 'none legal'))
    print(f'top edges found                  : {st["edges"]}')
    print(f'chained into runs                : {st["chains"]} '
          f'({st["raking_chains"]} raking)')
    print(f'seat depth m p5/25/50/75/95      : '
          + '/'.join(str(v) for v in st['seat_pct'].values()))
    print(f'chains too shallow for a profile : {st["unroutable"]}')
    print(f'faces the mesh gate rejected     : {st.get("dropped_faces", 0)}')
    print()
    print(f'{"profile":<16}{"runs":>7}{"stations":>10}{"blocks":>9}  '
          f'on the top edges of')
    for name in sorted(st['per_profile']):
        d = st['per_profile'][name]
        src = ', '.join(f'{k} x{v}' for k, v in sorted(d['from'].items(),
                                                       key=lambda kv: -kv[1]))
        print(f'{name:<16}{d["runs"]:>7}{d["stations"]:>10}{d["blocks"]:>9}  {src}')
    print()
    print(f'{"object":<20}{"before":>10}{"added":>10}')
    for m in sorted(set(per_base) | set(per_add)):
        print(f'{m:<20}{per_base.get(m, 0):>10}{per_add.get(m, 0):>10}')
    print(f'{"TOTAL tris":<20}{tris_base:>10}{tris_add:>10}')
    print(f'delta {tris_add:+d} triangles, '
          f'{(tris_base + tris_add) / max(tris_base, 1):.2f}x')
    print('=' * 72)


if __name__ == '__main__':
    main()
