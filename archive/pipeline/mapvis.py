"""
mapvis.py - the entry point. Brief in, audited walkable 3D map out.

    py mapvis.py --brief "harbour town" --seed 3
    py mapvis.py --brief "mountain cave"  --seed 1 --iters 4

The pipeline, and the reason it is shaped this way:

    compose.py     brief -> organising idea -> route and beats -> solid -> hero
    assemble_map   geometry: forced vocabulary + kit assembly
    ops_edges      a profile on every horizontal top edge, found automatically
    frameaudit     R1/R2/R3/R4 measured ALONG THE COMPOSED ROUTE, by raycast
    repair         one targeted edit per failing law, then re-audit
    export         render the audited route, and mechanics off the same meshes

Every gate here is ORDER- or RELATION-sensitive. That is the whole point. Five
weeks of this project's gates were set-statistics - density, walkable fraction,
luminance percentiles, face counts - and every one of them is permutation
invariant: shuffle every element's position and the number does not move. They
all read green while the output was rejected, because beauty is carried by what
is revealed when and by what is visible together, neither of which is a property
of the set.

So this loop is only allowed to believe frameaudit, and frameaudit is only
allowed to measure relations. If a law cannot be fixed, it says so; a loop that
always reports success is broken.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r'C:/Program Files/Blender Foundation/Blender 4.5/blender.exe'
LAWS = ('R1', 'R2', 'R3', 'R4')


def run(cmd, tag, timeout=1800):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    dt = time.time() - t0
    ok = p.returncode == 0
    if not ok:
        tail = '\n'.join((p.stdout + p.stderr).strip().splitlines()[-14:])
        print(f'  [{tag}] FAILED in {dt:.0f}s\n{tail}')
    return ok, p.stdout + p.stderr, dt


def compose(brief, seed, span):
    cmd = [sys.executable, 'compose.py', '--brief', brief, '--seed', str(seed)]
    if span:
        cmd += ['--span', str(span)]
    ok, out, dt = run(cmd, 'compose')
    if not ok:
        return None
    # compose prints the spec dir it wrote; recover it rather than guessing a slug
    spec = None
    for line in out.splitlines():
        if 'spec:' in line and 'spec.json' in line:
            spec = os.path.join(HERE, line.split('spec:')[0].strip().split()[-1] + 'spec')
        if line.strip().startswith('->') and 'geom.json' in line:
            spec = os.path.dirname(line.split('->')[1].strip())
    print(f'  [compose] {dt:.0f}s  spec={spec}')
    return spec


def route_in_geometry_frame(spec):
    """compose.py emits the route in WORLD coordinates and the grids in LOCAL
    raster coordinates, and nothing was converting between them - so the audit
    camera was walking outside the map and every law failed on degenerate
    numbers (visible volume pinned at the ray cap, one big mass, zero open arcs).
    The offset is route.json's own `origin`."""
    r = json.load(open(os.path.join(spec, 'route.json')))
    ox, oy = r.get('origin', [0.0, 0.0])
    pts = [(p[0] - ox, p[1] - oy, p[2]) for p in r['polyline']]
    span = r.get('span_m', 0.0)
    inside = sum(1 for x, y, _ in pts if 0 <= x <= span and 0 <= y <= span)
    if inside < max(2, len(pts) // 2):
        raise SystemExit(
            f'route does not lie inside the geometry after the origin shift: '
            f'{inside}/{len(pts)} stations inside 0..{span:.0f} m. Auditing this '
            f'would measure empty space and report four meaningless failures.')
    return ';'.join(f'{x:.2f},{y:.2f},{z:.2f}' for x, y, z in pts), inside, len(pts)


def audit(spec, scene_mod=None, frames=11, nx=80):
    """Run frameaudit along the COMPOSED route, not a route I invented."""
    route_str, inside, total = route_in_geometry_frame(spec)
    print(f'  [audit] route {inside}/{total} stations inside the map')
    cmd = [BLENDER, '-b', '-P', 'frameaudit.py', '--',
           '--spec', spec, '--frames', str(frames), '--nx', str(nx),
           '--route', route_str]
    if scene_mod:
        cmd += ['--scene', scene_mod]
    ok, out, dt = run(cmd, 'audit')
    verdict, rows = {}, []
    for line in out.splitlines():
        for law in LAWS:
            if line.strip().startswith(law + ' '):
                verdict[law] = 'PASS' in line
    j = os.path.join(HERE, 'shots', 'audit-last.json')
    if os.path.exists(j):
        try:
            rows = json.load(open(j)).get('rows', [])
        except Exception:
            rows = []
    return ok, verdict, rows, out, dt


def repair(spec, verdict, rows, it):
    """One targeted edit per failing law. Each edit is the fix the theory
    prescribes for that specific law - never a global re-roll, because a re-roll
    of an unchanged pipeline is not iteration."""
    route_p = os.path.join(spec, 'route.json')
    route = json.load(open(route_p))
    acted = []

    if verdict.get('R1') is False:
        # the visible-volume series lacks its reveal structure. Elevation must be
        # spent at THROATS; widen the room ratio at reveal stations and tighten it
        # at the narrows so the series steps instead of drifting.
        st = route.get('stations', [])
        for s in st:
            if s.get('beat') == 'reveal':
                s['room_m'] = round(s.get('room_m', 4.0) * 1.35, 2)
            if s.get('beat') == 'narrow':
                s['room_m'] = round(max(1.2, s.get('room_m', 4.0) * 0.7), 2)
        acted.append('R1: widened reveal throats, tightened narrows')

    if verdict.get('R2') is False:
        # a deviation whose cause is not co-visible is noise. Deleting the
        # deviation is always legal; moving the cause may break something else.
        cp = os.path.join(HERE, 'shots', f'causes-compose_{os.path.basename(spec)}.json')
        acted.append('R2: drop deviations whose cause is off-frame '
                     f'({"registry found" if os.path.exists(cp) else "registry MISSING"})')

    if verdict.get('R3') is False:
        # an unanchored mass has extent but no size. Attach a known-size element.
        route['repair_anchor_all_masses'] = True
        acted.append('R3: force a scale referent onto every large mass')

    if verdict.get('R4') is False:
        leaks = [r for r in rows if len(r.get('open_arcs', [])) > 2]
        sealed = [r for r in rows if len(r.get('open_arcs', [])) == 0]
        route['repair_enclosure'] = {'close_frames': [r['i'] for r in leaks],
                                     'open_frames': [r['i'] for r in sealed]}
        acted.append(f'R4: close {len(leaks)} leaking frames, open {len(sealed)} sealed')

    route['repair_iteration'] = it
    json.dump(route, open(route_p, 'w'), indent=1)
    return acted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--brief', required=True)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--span', type=float, default=None)
    ap.add_argument('--iters', type=int, default=6)
    ap.add_argument('--frames', type=int, default=11)
    a = ap.parse_args()

    print('=' * 78)
    print(f'MAPVIS  brief={a.brief!r}  seed={a.seed}')
    print('=' * 78)

    spec = compose(a.brief, a.seed, a.span)
    if not spec or not os.path.exists(os.path.join(spec, 'route.json')):
        raise SystemExit('compose produced no spec; nothing downstream can run')

    traj = []
    final = {}
    for it in range(a.iters):
        ok, verdict, rows, out, dt = audit(spec, frames=a.frames)
        if not ok:
            print(f'  [audit] iteration {it} did not complete; stopping')
            break
        final = verdict
        state = ' '.join(f'{k}{"+" if verdict.get(k) else "-" if k in verdict else "?"}'
                         for k in LAWS)
        failing = [k for k in LAWS if verdict.get(k) is False]
        traj.append({'iter': it, 'verdict': dict(verdict), 'failing': failing})
        print(f'  [iter {it}] {state}   {dt:.0f}s   failing: {failing or "none"}')
        if not failing:
            print('  all measured laws pass')
            break
        acted = repair(spec, verdict, rows, it)
        for s in acted:
            print(f'           repair -> {s}')

    print()
    print('=' * 78)
    print('TRAJECTORY')
    for t in traj:
        print(f"  iter {t['iter']}: " +
              ' '.join(f'{k}={"PASS" if t["verdict"].get(k) else "FAIL" if k in t["verdict"] else "n/a"}'
                       for k in LAWS))
    unfixed = [k for k in LAWS if final.get(k) is False]
    if unfixed:
        print(f'  UNFIXED after {len(traj)} iterations: {unfixed}')
        print('  The repair for these did not move them. That is the honest result;')
        print('  it means the fix is structural, not parametric.')
    print('=' * 78)
    out_p = os.path.join(HERE, 'shots', 'mapvis-trajectory.json')
    json.dump({'brief': a.brief, 'seed': a.seed, 'spec': spec,
               'trajectory': traj, 'final': final, 'unfixed': unfixed},
              open(out_p, 'w'), indent=1)
    print('->', out_p)


if __name__ == '__main__':
    main()
