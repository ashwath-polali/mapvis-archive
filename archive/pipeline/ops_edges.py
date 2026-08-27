"""
ops_edges.py - the edge operator. Finds every horizontal top edge in a mesh by
topology and runs a moulded section along it.

Why this file exists. THE-PICTURE.md section 6 item 6, on what extruded footprints
structurally cannot produce: "Extrusion gives a flat cap. The library has no flat
caps: coping, dentils, merlons, moulded stringcourses, blind arcading, pinnacle
finials, raked coping that follows a stair flight. This one omission is the largest
single reason terraces read as a contour diagram." Section 7 step 4 then names the
fix as the single highest-leverage mechanical change available.

The load-bearing design decision is that the CALLER NEVER SAYS WHERE THE EDGES ARE.
assemble_map.py emits tens of thousands of faces from rules; nobody is going to
enumerate their rims, and an element the assembler has to be told to place is just
another element. So the rims are read out of mesh topology: an edge is a top edge
when exactly one of the faces using it faces up. That is true of the open rim of a
cap (one face) and of a cap/wall junction (two faces, one up), and false of the
interior edges of a subdivided cap and of the ridge of a pitched roof, where both
faces face up. No caller input, no guessing, no model looking at anything.

Two things this deliberately does NOT do:
  - it does not judge whether the result looks better. Nothing here can.
  - it does not add a random offset anywhere. CONSTRUCTION-THEORY L2's corollary
    forbids raw jitter, and every number below is either a section dimension or a
    measured quantity read off the mesh.

Every dimension goes through kit/_geom.check_char at import time, so an out-of-band
edit fails on import rather than in a render.

    python ops_edges.py            # self-test: gates, topology, sweeps, chamfer
"""
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, 'kit')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _geom as G
from _geom import CHAR, ScaleError, check_char          # noqa: F401  (re-exported)


# ===========================================================================
# THE PROFILE LIBRARY
#
# A section is a list of (u, v) in metres: u is the OUTWARD lateral offset from
# the found edge (positive = past the exposed face, negative = inboard, seated on
# the surface the edge terminates), v is height above the edge. `seat` is how much
# inboard surface the section needs, which is what stops a 0.42 m coping being run
# along a 0.24 m stair tread.
#
# `drop` shifts the whole run in z: 0 for anything that caps the edge, negative for
# a band that hangs below it.
#
# `rep` is a repeating solid at a fixed beat, for the profiles that are not a
# continuous section - dentils, merlons, arcade piers. z0/z1 are relative to the
# dropped edge height, u is the block centre's lateral offset.
# ===========================================================================

PROFILES = {

    # Weathered oversailing coping. The default termination for a wall head, a
    # terrace lip or a quay edge. The top falls outward to shed water, the front
    # oversails the face, and a drip bead on the soffit throws the run-off clear -
    # which is also what puts a hard shadow line under the whole length.
    'coping': {
        'sect': [(-0.420, 0.000), (0.010, 0.000), (0.010, -0.038), (0.050, -0.038),
                 (0.050, 0.000), (0.095, 0.000), (0.095, 0.125), (-0.420, 0.170)],
        'drop': -0.050, 'seat': 0.42, 'rake_ok': False, 'rep': None,
        'gates': [('coping bed', 0.170, 0.09, 0.18),
                  ('coping oversail', 0.095, 0.04, 0.08),
                  ('coping weather fall', 0.045, 0.02, 0.05),
                  ('coping seat', 0.420, 0.20, 0.30)],
    },

    # The same family proportioned for a stair cheek, and the ONLY profile legal on
    # a raking chain. It rakes with the flight because the sweep places every ring
    # at that station's own z and keeps the section plumb - so the coping's angle
    # is the flight's angle by construction and cannot be anything else. The drip
    # bead is dropped: at a 0.21 m riser it would read as noise.
    'raked_coping': {
        'sect': [(-0.300, 0.000), (0.075, 0.000), (0.075, 0.100), (-0.300, 0.145)],
        'drop': -0.040, 'seat': 0.30, 'rake_ok': True, 'rep': None,
        'gates': [('raked coping bed', 0.145, 0.07, 0.16),
                  ('raked coping oversail', 0.075, 0.03, 0.07),
                  ('raked coping seat', 0.300, 0.15, 0.25)],
    },

    # A pier or wall head: fillet, flare, chamfered return, weathered top. Three
    # steps rather than one slab, because a single slab reads as the flat cap this
    # operator exists to delete.
    'moulded_cap': {
        'sect': [(-0.340, 0.000), (0.050, 0.000), (0.050, 0.060), (0.110, 0.095),
                 (0.110, 0.165), (0.040, 0.240), (-0.340, 0.280)],
        'drop': -0.060, 'seat': 0.34, 'rake_ok': False, 'rep': None,
        'gates': [('moulded cap height', 0.280, 0.12, 0.20),
                  ('moulded cap projection', 0.110, 0.04, 0.09),
                  ('moulded cap seat', 0.340, 0.15, 0.28)],
    },

    # A thin projecting band a storey below the head. It does nothing to the top
    # edge; it puts a horizontal shadow across a blank wall, which is the other
    # half of why a reference facade never reads as one plane.
    'string_course': {
        'sect': [(-0.240, 0.000), (0.055, 0.000), (0.075, 0.035), (0.075, 0.100),
                 (-0.240, 0.125)],
        'drop': -3.200, 'seat': 0.24, 'rake_ok': False, 'rep': None,
        'gates': [('string course height', 0.125, 0.05, 0.11),
                  ('string course projection', 0.075, 0.03, 0.07),
                  ('string course drop', 3.200, 1.60, 2.10)],
    },

    # A kerb upstand for a paving or terrace rim: small seat, chamfered top arris
    # so the edge catches light instead of vanishing.
    'kerb': {
        'sect': [(-0.220, 0.000), (0.060, 0.000), (0.060, 0.085),
                 (0.025, 0.125), (-0.220, 0.125)],
        'drop': -0.030, 'seat': 0.22, 'rake_ok': False, 'rep': None,
        'gates': [('kerb upstand', 0.125, 0.05, 0.10),
                  ('kerb width', 0.280, 0.12, 0.22)],
    },

    # A tread nosing: the smallest member in the library, and the fallback when the
    # up-surface behind an edge is too shallow to seat anything else. Projects past
    # the riser and undercuts, so each tread throws its own shadow.
    'nosing': {
        'sect': [(-0.160, 0.000), (0.038, 0.000), (0.038, -0.028),
                 (0.010, -0.042), (-0.160, -0.042)],
        'drop': 0.000, 'seat': 0.16, 'rake_ok': True, 'rep': None,
        'gates': [('nosing projection', 0.038, 0.015, 0.030),
                  ('nosing depth', 0.042, 0.015, 0.030),
                  ('nosing seat', 0.160, 0.07, 0.13)],
    },

    # Continuous fillet plus a dentil course. The blocks are one brick end each and
    # at a 0.22 m beat they read as a texture band at distance and as individual
    # members close up, which is exactly what a dentil course is for.
    'dentil_band': {
        'sect': [(-0.300, 0.000), (0.050, 0.000), (0.050, 0.090), (-0.300, 0.090)],
        'drop': -0.300, 'seat': 0.30, 'rake_ok': False,
        'rep': {'pitch': 0.220,
                'blocks': [{'along': 0.110, 'across': 0.110, 'u': 0.105,
                            'z0': -0.110, 'z1': 0.000}]},
        'gates': [('dentil band height', 0.090, 0.04, 0.09),
                  ('dentil block', 0.110, 0.04, 0.09),
                  ('dentil pitch', 0.220, 0.09, 0.16)],
    },

    # Merlons on a bed course, with the crenels as the gaps. Chunky: 0.62 m of
    # merlon at a 1.05 m beat, which is the measured reference proportion, not a
    # fine picket rhythm.
    'merlon_run': {
        'sect': [(-0.360, 0.000), (0.060, 0.000), (0.060, 0.160), (-0.360, 0.160)],
        'drop': 0.000, 'seat': 0.36, 'rake_ok': False,
        'rep': {'pitch': 1.050,
                'blocks': [{'along': 0.620, 'across': 0.420, 'u': -0.150,
                            'z0': 0.160, 'z1': 0.780}]},
        'gates': [('merlon height', 0.620, 0.28, 0.50),
                  ('merlon width', 0.620, 0.28, 0.50),
                  ('merlon pitch', 1.050, 0.50, 0.80),
                  ('merlon bed', 0.160, 0.07, 0.14)],
    },

    # Blind arcading: a continuous impost band with pilaster piers hanging off it
    # and a corbel at each pier head. The arch heads are CORBELLED STEPS, not arcs -
    # a true arc needs a section swept in the vertical plane, which this operator
    # does not do, and a stepped corbel is itself a reference form rather than a
    # fudge. The voids between the piers are what read as the recessed bays.
    'blind_arcade': {
        'sect': [(-0.260, 0.000), (0.050, 0.000), (0.050, 0.110), (-0.260, 0.110)],
        'drop': -0.100, 'seat': 0.26, 'rake_ok': False,
        'rep': {'pitch': 1.150,
                'blocks': [{'along': 0.260, 'across': 0.200, 'u': 0.100,
                            'z0': -1.450, 'z1': 0.000},
                           {'along': 0.520, 'across': 0.130, 'u': 0.065,
                            'z0': -0.340, 'z1': -0.120}]},
        'gates': [('arcade pier width', 0.260, 0.11, 0.20),
                  ('arcade pier height', 1.450, 0.65, 1.15),
                  ('arcade bay pitch', 1.150, 0.55, 0.85),
                  ('arcade impost', 0.110, 0.05, 0.10)],
    },
}


# A section whose inboard arris lands exactly on the far edge of the surface it
# seats on has nothing to bear on, so the seat it needs is its inboard reach plus a
# third. This is the number that decides a 0.24 m stair tread takes a nosing and a
# 3 m terrace takes a coping, without anyone looking at either.
SEAT_MARGIN = 1.35


def seat_needed(profile):
    return SEAT_MARGIN * PROFILES[profile]['seat']


def _gate_profiles():
    """Run every profile's dimensions through the kit's CHAR gate at import, and
    check each section is a simple polygon whose extents agree with its own gates.
    A profile that fails here must be fixed, never widened."""
    for name, p in PROFILES.items():
        for label, m, lo, hi in p['gates']:
            check_char(f'{name}.{label}', m, lo, hi)
        us = [u for u, _ in p['sect']]
        if -min(us) > p['seat'] + 1e-9:
            raise ScaleError(f'{name}: section reaches {-min(us):.3f} m inboard '
                             f'but declares seat {p["seat"]:.3f} m')
        if G._area([(u, v, 0.0) for u, v in p['sect']]) < 1e-5:
            raise ScaleError(f'{name}: section has no area')


_gate_profiles()


# ===========================================================================
# 1. FIND THE EDGES
# ===========================================================================

def _face_normal(verts, face):
    """Newell normal, unnormalised. Positive z for a polygon wound CCW seen from
    above, which is what lets the up-face's own traversal direction give the
    outward side for free."""
    nx = ny = nz = 0.0
    n = len(face)
    for i in range(n):
        a, b = verts[face[i]], verts[face[(i + 1) % n]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return nx, ny, nz


def find_top_edges(verts, faces, min_len=0.30, up_thresh=0.55,
                   min_rake=0.0, max_rake=0.18, max_len=50.0):
    """Every edge that terminates an upward-facing surface, oriented and measured.

    An edge qualifies when exactly ONE of the faces using it faces up (normal z
    over `up_thresh` after normalising). That single test covers the open rim of a
    cap and the cap/wall junction, and rejects both the interior edges of a
    subdivided cap and the ridge of a pitched roof.

    Returns a list of dicts: `a`, `b` (3D ends, oriented so the right-hand plan
    normal (t.y, -t.x) points AWAY from the up-face, which is the sign convention
    _geom.plan_frames and sweep_section already use), `seat` (how far the up-face
    extends inboard from this edge, in plan), `rake` (|dz| / plan length).

    Orientation is exact rather than heuristic: the up-face is CCW seen from above
    by definition of the normal test, so walking a->b in the FACE's own order keeps
    the face on the left and the outside on the right. A centroid test would get
    this wrong on any concave rim, and every traced terrace loop is concave.

    `min_rake`/`max_rake` select which family of edges is wanted: the default band
    is the near-horizontal ones, and raising min_rake finds the raking flanks of a
    stair flight for raked_coping.

    `min_len` is a numerical-sliver floor, not the length filter that matters: a
    curved terrace rim arrives as dozens of 0.4 m segments and must not be thrown
    away one segment at a time. Run length is filtered after chaining, by
    run_profile's `min_run`.

    `max_len` exists because assemble_map's sea is one 4-vertex prism spanning 3.8x
    the map, so its rim edges are 760 m and are not architectural edges. Everything
    vectorise traces is simplified at 2.2 m, so no built edge in this pipeline comes
    near 50 m.

    Edges are matched by rounded POSITION, not by vertex index, because half the
    geometry reaching this operator comes from kit/_geom.Mesh, which is a quad soup
    that mints four fresh vertices per face. Index matching welds nothing there, so
    every rim edge looks like a boundary and a roof ridge comes back as two top
    edges instead of none. That was measured, not guessed - the ridge test in the
    self-test is the one that caught it.
    """
    q = 1e-3

    def pk(p):
        return (round(p[0] / q), round(p[1] / q), round(p[2] / q))

    ed = {}
    for fi, face in enumerate(faces):
        if len(face) < 3:
            continue
        nx, ny, nz = _face_normal(verts, face)
        L = math.sqrt(nx * nx + ny * ny + nz * nz)
        if L < 1e-12:
            continue
        n = len(face)
        isup = (nz / L) >= up_thresh
        ks = [pk(verts[i]) for i in face]
        for k in range(n):
            ka, kb = ks[k], ks[(k + 1) % n]
            key = (ka, kb) if ka <= kb else (kb, ka)
            e = ed.get(key)
            if e is None:
                e = ed[key] = [0, 0, None]
            if isup:
                e[0] += 1
                e[2] = (face[k], face[(k + 1) % n], fi)
            else:
                e[1] += 1

    out = []
    for nup, _ndown, up in ed.values():
        if nup != 1 or up is None:
            continue
        i, j, fi = up
        face = faces[fi]
        pa, pb = verts[i], verts[j]
        dx, dy, dz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        h = math.hypot(dx, dy)
        if h < 1e-9:
            continue
        seg = math.sqrt(h * h + dz * dz)
        if seg < min_len or seg > max_len:
            continue
        rake = abs(dz) / h
        if rake < min_rake or rake > max_rake:
            continue
        inx, iny = -dy / h, dx / h                 # inboard = left of travel
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        seat = 0.0
        for vi in face:
            p = verts[vi]
            seat = max(seat, (p[0] - mx) * inx + (p[1] - my) * iny)
        out.append({'a': (pa[0], pa[1], pa[2]), 'b': (pb[0], pb[1], pb[2]),
                    'seat': seat, 'rake': rake, 'len': seg})
    return out


def chain_edges(edges, tol=0.02):
    """Order the oriented segments into runs, so one sweep call covers a whole rim.

    Consistent orientation in means a consistent outward normal out. Runs are
    grown backward then forward from each unused seed, so a chain is never split in
    two by the order the edges happened to come out of the dict. At a branch vertex
    (two rims meeting) the first unused edge wins, which is arbitrary but
    deterministic - there is no correct answer and nothing here may invent one.

    Returns [{'pts': [...3D...], 'closed': bool, 'seat': min over edges,
              'rake': max over edges, 'plan_len': float}, ...]
    """
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))

    by_start, by_end = {}, {}
    for i, e in enumerate(edges):
        by_start.setdefault(key(e['a']), []).append(i)
        by_end.setdefault(key(e['b']), []).append(i)
    used = [False] * len(edges)

    def take(bucket, k):
        for j in bucket.get(k, ()):
            if not used[j]:
                used[j] = True
                return j
        return None

    chains = []
    for s in range(len(edges)):
        if used[s]:
            continue
        used[s] = True
        run = [s]
        while True:
            j = take(by_end, key(edges[run[0]]['a']))
            if j is None or j == run[0]:
                break
            run.insert(0, j)
            if key(edges[run[0]]['a']) == key(edges[run[-1]]['b']):
                break
        while True:
            j = take(by_start, key(edges[run[-1]]['b']))
            if j is None:
                break
            run.append(j)
            if key(edges[run[-1]]['b']) == key(edges[run[0]]['a']):
                break
        pts = [edges[run[0]]['a']] + [edges[i]['b'] for i in run]
        closed = len(pts) > 3 and key(pts[0]) == key(pts[-1])
        if closed:
            pts.pop()
        plan = sum(math.dist(pts[i][:2], pts[(i + 1) % len(pts)][:2])
                   for i in range(len(pts) if closed else len(pts) - 1))
        chains.append({'pts': pts, 'closed': closed, 'plan_len': plan,
                       'seat': min(edges[i]['seat'] for i in run),
                       'rake': max(edges[i]['rake'] for i in run)})
    return chains


# ===========================================================================
# 2. RUN THE SECTION
# ===========================================================================

def _stations3(path, closed, pitch):
    """Fixed-beat stations with their 3D position and plan tangent. _geom.stations
    returns 2D only, and a raking run needs the z or the blocks float."""
    n = len(path)
    segs, total = [], 0.0
    for i in range(n if closed else n - 1):
        a, b = path[i], path[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-9:
            segs.append((a, b, L, total))
            total += L
    if total <= 1e-6 or not segs:
        return []
    k = max(1, int(round(total / pitch)))
    out = []
    for q in range(k):
        s = total * (q + 0.5) / k
        a, b, L, s0 = segs[-1]
        for cand in segs:
            if s <= cand[3] + cand[2] + 1e-9:
                a, b, L, s0 = cand
                break
        t = max(0.0, min(1.0, (s - s0) / L))
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                    a[2] + (b[2] - a[2]) * t, (b[0] - a[0]) / L, (b[1] - a[1]) / L))
    return out


def run_profile(loops, profile, mat='stone_course', drop=None, min_run=1.2,
                mesh=None):
    """Sweep a named section along every chain, mitred at every corner.

    Corners are mitred by _geom.plan_frames: each station is offset along the
    angle bisector of its two segments and scaled by 1/cos(half-turn), so the
    section's width survives the turn instead of pinching to nothing on the inside
    and gapping on the outside. That is the whole difference between a run of
    moulding and a row of separate sticks.

    A raking chain gets its rings placed at each station's own z with the section
    kept plumb, so a raked profile takes the flight's angle by construction. Any
    profile without rake_ok is refused on a raking chain rather than laid flat
    across it.

    Returns (mesh, stats). `mesh` is a _geom.Mesh so several profiles can be
    accumulated into one before it is handed to a renderer.
    """
    p = PROFILES[profile]
    m = mesh if mesh is not None else G.Mesh()
    dz = p['drop'] if drop is None else drop
    st = {'runs': 0, 'stations': 0, 'blocks': 0,
          'skipped_short': 0, 'skipped_seat': 0, 'skipped_rake': 0}

    for ch in loops:
        pts, closed = (ch['pts'], ch['closed']) if isinstance(ch, dict) else (ch, False)
        if len(pts) < 2:
            st['skipped_short'] += 1
            continue
        rake = ch.get('rake', 0.0) if isinstance(ch, dict) else 0.0
        seat = ch.get('seat', 1e9) if isinstance(ch, dict) else 1e9
        plan = ch.get('plan_len') if isinstance(ch, dict) else None
        if plan is None:
            plan = sum(math.dist(pts[i][:2], pts[(i + 1) % len(pts)][:2])
                       for i in range(len(pts) if closed else len(pts) - 1))
        if plan < min_run:
            st['skipped_short'] += 1
            continue
        if rake > 0.05 and not p['rake_ok']:
            st['skipped_rake'] += 1
            continue
        if seat + 1e-6 < seat_needed(profile):
            st['skipped_seat'] += 1
            continue

        path = [(q[0], q[1], q[2] + dz) for q in pts]
        G.sweep_section(m, path, p['sect'], mat=mat, side=1.0,
                        closed_path=closed, cap=True)
        st['runs'] += 1
        st['stations'] += len(path)

        rep = p['rep']
        if rep:
            for (px, py, pz, tx, ty) in _stations3(path, closed, rep['pitch']):
                for b in rep['blocks']:
                    quad = G.rect_at(px, py, tx, ty, b['along'], b['across'], u=b['u'])
                    G.prism(m, quad, pz + b['z0'], pz + b['z1'], mat=mat,
                            cap_top=True, cap_bot=False)
                    st['blocks'] += 1
    return m, st


# ===========================================================================
# 3. CHAMFER
# ===========================================================================

def chamfer_corners(loop, cut=0.9, min_turn=55.0, closed=True,
                    spike_turn=None, want_piers=False):
    """Replace every sharp plan turn with a canted return, and report the turns too
    sharp to cant, which take a quoined pier stop instead.

    Measured 2026-07-28 across bolderfall-20 / montwise-18 / steam-river-26 /
    canalbrine-church-stairs-12 / atlasdam-22: an Octopath retaining plan NEVER has
    a raw 90-degree corner. Every plan turn is a 45-degree canted return or a
    quoined pier stop. A Douglas-Peucker trace produces nothing but raw corners,
    which is a measurable reason our walls read as engineering.

    Moved here from vectorise.py:chamfer with four fixes that version needed:
      - coincident points are dropped first, so a duplicated vertex cannot produce
        a garbage tangent and a spurious cant out of nothing
      - z is interpolated along each leg instead of copied from the corner, so a
        raking run stays straight after chamfering instead of gaining two steps
      - a near-reversal can be collapsed rather than canted; canting a spike folds
        the loop back through itself and the sweep self-intersects
      - the too-sharp turns come back as PIER STOPS, because the measurement says
        both terminations exist and only one of them was ever built

    `spike_turn` is OFF by default, and deliberately. Measured on
    place/villefranche/spec: collapsing reversals above 148 degrees takes the block
    count from 93 to 87 and the terrace vertex count from 365 to 363, because some
    traced blocks are slivers that only survive as spikes. That may well be the
    right answer, but it is a change to the map, not to this operator, and it is
    not this session's to make. Pass a value to opt in. The other three fixes are
    output-neutral on that spec, verified by regenerating geom.json both ways.

    Points come back with the same dimensionality they went in with, so the 2D
    callers in vectorise.py are unaffected.

    Returns the point list, or (points, piers) when want_piers, where each pier is
    (x, y, z, bearing) with the bearing along the outgoing leg.
    """
    dim3 = any(len(q) > 2 for q in loop)
    pts = []
    for q in loop:
        q = tuple(q[:3]) + ((0.0,) if len(q) < 3 else ())
        if not pts or math.dist(q[:2], pts[-1][:2]) > 1e-6:
            pts.append(q)
    if closed and len(pts) > 1 and math.dist(pts[0][:2], pts[-1][:2]) <= 1e-6:
        pts.pop()
    n = len(pts)
    if n < 3:
        pts = pts if dim3 else [p[:2] for p in pts]
        return (pts, []) if want_piers else pts

    out, piers = [], []
    rng = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(pts[0])
    for i in rng:
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        l1 = math.dist(a[:2], b[:2]) or 1e-9
        l2 = math.dist(b[:2], c[:2]) or 1e-9
        v1 = ((b[0] - a[0]) / l1, (b[1] - a[1]) / l1)
        v2 = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
        turn = math.degrees(math.acos(max(-1.0, min(1.0, v1[0] * v2[0] + v1[1] * v2[1]))))
        if turn < min_turn:
            out.append(b)
            continue
        if spike_turn is not None and turn > spike_turn:
            # a reversal. There is no cant that does not cross the incoming leg,
            # so drop the vertex and let the two legs meet as one.
            continue
        d = min(cut, 0.4 * l1, 0.4 * l2)
        t1, t2 = d / l1, d / l2
        out.append((b[0] - v1[0] * d, b[1] - v1[1] * d, b[2] + (a[2] - b[2]) * t1))
        out.append((b[0] + v2[0] * d, b[1] + v2[1] * d, b[2] + (c[2] - b[2]) * t2))
        if turn > 100.0:
            piers.append((b[0], b[1], b[2], math.atan2(v2[1], v2[0])))
    if not closed:
        out.append(pts[-1])
    if not dim3:
        out = [p[:2] for p in out]
    return (out, piers) if want_piers else out


# ===========================================================================
# 4. THE AUTOMATIC SWEEP OVER A WHOLE MAP
# ===========================================================================

# source material -> the profile family its top edges take. This is a routing
# table, not a beauty claim: it says which member of the library terminates which
# kind of surface, and it is swappable data.
RULES = {
    'cobble':         ('kerb',        'stone_course'),
    'dirt':           ('kerb',        'stone_course'),
    'quay_block':     ('coping',      'stone_course'),
    'stone_course':   ('coping',      'stone_course'),
    'brick':          ('moulded_cap', 'stone_course'),
    'plaster_timber': ('moulded_cap', 'stone_course'),
    'shingle':        ('moulded_cap', 'shingle'),
    'plank':          (None,          None),
}

# when the up-surface behind an edge is too shallow to seat the first choice, fall
# down the ladder rather than burying it. A stair tread is 0.24 m deep; a 0.42 m
# coping run along it would swallow the flight whole.
LADDER = {
    'coping':       ('coping', 'kerb', 'nosing'),
    'moulded_cap':  ('moulded_cap', 'kerb', 'nosing'),
    'kerb':         ('kerb', 'nosing'),
    'raked_coping': ('raked_coping', 'nosing'),
    'merlon_run':   ('merlon_run', 'coping', 'kerb'),
}

# a second band on the mass materials: a storey below the head.
SECOND = {'brick': ('string_course', 'stone_course'),
          'plaster_timber': ('string_course', 'stone_course')}

# There is deliberately NO rule here that routes tower heads to merlon_run. The
# obvious one - a short closed rim above some height - was written, run, and thrown
# out: it fired on 444 of the 444 mass heads in place/villefranche and pre-empted
# moulded_cap entirely, because the test was on absolute world z and this is a hill
# town whose terrain alone reaches 27 m. Height above a mass's OWN base is the
# quantity that rule needs and it is not recoverable from a rim, so the rule does
# not belong in this operator. merlon_run stays in the library for a caller that
# knows what a tower is.


def _pick(family, seat, rake):
    for name in LADDER.get(family, (family,)):
        p = PROFILES[name]
        if rake > 0.05 and not p['rake_ok']:
            continue
        if seat + 1e-6 >= seat_needed(name):
            return name
    return None


def apply_to_parts(parts, rules=None, second=None, verbose=True):
    """The point of the whole file: take a map's (material, verts, faces) parts,
    find every top edge in every one of them, and run a section along all of them.

    No caller says where anything is. The only inputs are the parts themselves and
    the routing table.

    Returns (new_parts, stats) where new_parts is in the same (material, verts,
    faces) form the assembler already emits, so it appends and nothing downstream
    changes.
    """
    rules = RULES if rules is None else rules
    second = SECOND if second is None else second
    meshes, stats = {}, {'edges': 0, 'chains': 0, 'per_profile': {},
                         'raking_chains': 0, 'seats': [], 'unroutable': 0,
                         'focus': None}
    focus_len = -1.0

    def acc(mat):
        return meshes.setdefault(mat, G.Mesh())

    def bump(name, st, src, n):
        d = stats['per_profile'].setdefault(name, {'runs': 0, 'stations': 0,
                                                   'blocks': 0, 'from': {}})
        for k in ('runs', 'stations', 'blocks'):
            d[k] += st[k]
        d['from'][src] = d['from'].get(src, 0) + n

    for mat, verts, faces in parts:
        family, outmat = rules.get(mat, (None, None))
        if family is None:
            continue
        # one topology pass over the whole rake band, then partitioned. Chaining
        # them together would let a terrace rim that happens to touch a stair flank
        # inherit the flank's rake and take the whole run's profile with it.
        found = find_top_edges(verts, faces, max_rake=1.40)
        flat = [e for e in found if e['rake'] <= 0.18]
        rake = [e for e in found if e['rake'] >= 0.20]
        stats['edges'] += len(flat) + len(rake)

        for edges, fam in ((flat, family), (rake, 'raked_coping')):
            if not edges:
                continue
            chains = chain_edges(edges)
            stats['chains'] += len(chains)
            if fam == 'raked_coping':
                stats['raking_chains'] += len(chains)
            buckets = {}
            for ch in chains:
                stats['seats'].append(round(ch['seat'], 3))
                if fam == 'raked_coping' and ch['plan_len'] > focus_len:
                    focus_len = ch['plan_len']
                    q = ch['pts'][len(ch['pts']) // 2]
                    stats['focus'] = (round(q[0], 2), round(q[1], 2), round(q[2], 2))
                name = _pick(fam, ch['seat'], ch['rake'])
                if name:
                    buckets.setdefault(name, []).append(ch)
                else:
                    stats['unroutable'] += 1
            for name, chs in buckets.items():
                _, st = run_profile(chs, name, mat=outmat, mesh=acc(outmat))
                bump(name, st, mat, st['runs'])

        band = second.get(mat)
        if band:
            chains = [c for c in chain_edges(flat) if c['rake'] <= 0.05]
            _, st = run_profile(chains, band[0], mat=band[1], mesh=acc(band[1]),
                                min_run=5.0)
            bump(band[0], st, mat, st['runs'])

    out = []
    for mat, m in meshes.items():
        if m.v and m.f:
            out.append((mat, m.v, m.f))
        stats.setdefault('dropped_faces', 0)
        stats['dropped_faces'] += m.dropped
    stats['tris'] = sum(len(f) - 2 for _m, _v, fs in out for f in fs)
    s = sorted(stats['seats'])
    stats['seat_pct'] = {p: (s[min(len(s) - 1, int(len(s) * p / 100))] if s else None)
                         for p in (5, 25, 50, 75, 95)}
    if verbose:
        print(f'[edges] {stats["edges"]} top edges -> {stats["chains"]} chains '
              f'({stats["raking_chains"]} raking) -> {stats["tris"]} triangles')
        print(f'[edges] seat depth m, p5/25/50/75/95: '
              + '/'.join(str(v) for v in stats['seat_pct'].values())
              + f'   {stats["unroutable"]} chains too shallow for any profile')
        for name in sorted(stats['per_profile']):
            d = stats['per_profile'][name]
            print(f'[edges]   {name:<14} runs {d["runs"]:>5}  '
                  f'stations {d["stations"]:>6}  blocks {d["blocks"]:>6}')
    return out, stats


# ===========================================================================
# self-test
# ===========================================================================

def _selftest():
    ok = True

    def say(name, cond, extra=''):
        nonlocal ok
        ok = ok and cond
        print(f'  {"PASS" if cond else "FAIL"}  {name}  {extra}')

    print('profiles: all dimensions gated at import against CHAR = 1.7 m')
    print(f'  {len(PROFILES)} profiles: {", ".join(sorted(PROFILES))}')

    print('\ntopology: a 6 x 4 x 2 box')
    m = G.Mesh()
    G.box(m, 0, 0, 0, 6, 4, 2)
    e = find_top_edges(m.v, m.f, min_len=0.1)
    say('finds exactly the 4 top edges', len(e) == 4, f'got {len(e)}')
    say('every found edge is at z = 2', all(abs(q['a'][2] - 2) < 1e-9 for q in e))
    say('seat spans the box', all(q['seat'] > 3.9 for q in e),
        f'seats {[round(q["seat"], 2) for q in e]}')
    ch = chain_edges(e)
    say('the 4 edges chain into 1 closed loop',
        len(ch) == 1 and ch[0]['closed'], f'{len(ch)} chains')

    print('\ntopology: a subdivided cap must not gain interior edges')
    m2 = G.Mesh()
    G.box(m2, 0, 0, 0, 4, 4, 1, skip=('+z',))
    m2.quad((0, 0, 1), (2, 0, 1), (2, 4, 1), (0, 4, 1))
    m2.quad((2, 0, 1), (4, 0, 1), (4, 4, 1), (2, 4, 1))
    e2 = find_top_edges(m2.v, m2.f, min_len=0.1)
    say('two coplanar cap quads still give 6 rim edges, not 8',
        len(e2) == 6, f'got {len(e2)}')

    print('\ntopology: a 42-degree gable ridge is not a top edge')
    m3 = G.Mesh()
    zt = 2.0 + 2.0 * math.tan(math.radians(42))
    m3.quad((0, 0, 2), (6, 0, 2), (6, 2, zt), (0, 2, zt))
    m3.quad((6, 4, 2), (0, 4, 2), (0, 2, zt), (6, 2, zt))
    e3 = find_top_edges(m3.v, m3.f, min_len=0.1)
    zs = sorted(round(q['a'][2], 2) for q in e3)
    say('both pitches face up so the ridge is rejected',
        len(e3) == 2 and all(abs(z - 2.0) < 1e-6 for z in zs),
        f'edge heights {zs} (ridge would be {zt:.2f})')

    print('\norientation: outward side on a concave (L-shaped) cap')
    L = [(0, 0), (8, 0), (8, 3), (3, 3), (3, 8), (0, 8)]
    m4 = G.Mesh()
    G.prism(m4, L, 0, 2, cap_top=True)
    e4 = find_top_edges(m4.v, m4.f, min_len=0.1)
    say('6 rim edges on the L', len(e4) == 6, f'got {len(e4)}')
    inside = 0
    for q in e4:
        dx, dy = q['b'][0] - q['a'][0], q['b'][1] - q['a'][1]
        h = math.hypot(dx, dy)
        mx, my = (q['a'][0] + q['b'][0]) / 2, (q['a'][1] + q['b'][1]) / 2
        ox, oy = dy / h, -dx / h
        if _point_in(mx + ox * 0.2, my + oy * 0.2, L):
            inside += 1
    say('no edge points its outward side into the solid', inside == 0,
        f'{inside} inverted')

    print('\nsweep: coping on the box rim')
    mm, st = run_profile(ch, 'coping', mat='stone_course')
    say('one closed run', st['runs'] == 1, str(st))
    say('closed sweep emits no end caps',
        len(mm.f) == 4 * len(PROFILES['coping']['sect']),
        f'{len(mm.f)} faces for 4 stations x {len(PROFILES["coping"]["sect"])} pts')
    say('faces wind outward (positive volume)', G.signed_volume(mm) > 0,
        f'{G.signed_volume(mm):.3f}')
    good, bad = G.validate(mm)
    say('mesh validates', good, ';'.join(bad))
    lo, hi = mm.bbox()
    say('coping oversails the 6 x 4 box on all four sides',
        lo[0] < -0.09 and lo[1] < -0.09 and hi[0] > 6.09 and hi[1] > 4.09,
        f'bbox {tuple(round(v, 3) for v in lo)} {tuple(round(v, 3) for v in hi)}')

    print('\nsweep: every profile builds and validates')
    for name in sorted(PROFILES):
        mp, sp = run_profile([{'pts': [(0, 0, 3), (10, 0, 3), (10, 6, 3)],
                               'closed': False, 'seat': 2.0, 'rake': 0.0,
                               'plan_len': 16.0}], name, mat='stone_course')
        g, b = G.validate(mp)
        say(f'{name:<14}', g and mp.tris > 0 and sp['runs'] == 1,
            f'{mp.tris:>5} tris, {sp["blocks"]:>3} blocks, dropped {mp.dropped}'
            + ('  ' + ';'.join(b) if b else ''))

    print('\nsweep: mitre holds the section width through a 90-degree turn')
    mt, _ = run_profile([{'pts': [(0, 0, 0), (10, 0, 0), (10, 10, 0)],
                          'closed': False, 'seat': 2.0, 'rake': 0.0,
                          'plan_len': 20.0}], 'coping', mat='s')
    lo, hi = mt.bbox()
    say('the outer arris reaches the mitre point, not the corner',
        abs(hi[0] - (10 + 0.095)) < 0.02, f'max x {hi[0]:.3f} (want 10.095)')

    print('\nraked coping takes the flight angle, not its own')
    for rise, run in ((1.20, 2.40), (1.80, 5.40), (2.20, 3.30)):
        want = rise / run
        r, _ = run_profile([{'pts': [(0, 0, 0), (0, run, rise)], 'closed': False,
                             'seat': 1.0, 'rake': want, 'plan_len': run}],
                           'raked_coping', mat='s')
        y0, y1 = min(p[1] for p in r.v), max(p[1] for p in r.v)
        z0 = max(p[2] for p in r.v if abs(p[1] - y0) < 1e-6)
        z1 = max(p[2] for p in r.v if abs(p[1] - y1) < 1e-6)
        got = (z1 - z0) / (y1 - y0)
        say(f'rise {rise} over run {run}', abs(got - want) < 1e-12,
            f'coping top slope {got:.9f}, flight slope {want:.9f}')
    r2, s2 = run_profile([{'pts': [(0, 0, 0), (0, 3, 1)], 'closed': False,
                           'seat': 1.0, 'rake': 0.333, 'plan_len': 3.0}],
                         'coping', mat='s')
    say('a non-raking profile is refused on a raking chain',
        s2['runs'] == 0 and s2['skipped_rake'] == 1, str(s2))

    print('\nseat ladder (seat needed = inboard reach x 1.35)')
    for seat, want in ((0.10, None), (0.24, 'nosing'), (0.32, 'kerb'),
                       (0.50, 'moulded_cap'), (3.00, 'coping')):
        fam = 'moulded_cap' if want == 'moulded_cap' else 'coping'
        got = _pick(fam, seat, 0.0)
        say(f'seat {seat:.2f} m under {fam:<12}', got == want, f'-> {got}')
    say('a raking chain never gets a flat-topped profile',
        _pick('coping', 3.0, 0.4) == 'nosing', str(_pick('coping', 3.0, 0.4)))
    say('a raking chain gets raked_coping',
        _pick('raked_coping', 3.0, 0.4) == 'raked_coping')

    print('\nchamfer_corners')
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    c1 = chamfer_corners(sq, cut=0.9)
    say('4 raw corners become 8 canted points', len(c1) == 8, f'{len(c1)}')
    cants = [math.dist(c1[2 * i][:2], c1[2 * i + 1][:2]) for i in range(4)]
    say('every cant is a 45-degree return',
        all(abs(s - 0.9 * math.sqrt(2)) < 1e-9 for s in cants),
        f'cants {[round(s, 4) for s in cants]}, want {0.9 * math.sqrt(2):.4f}')
    c2 = chamfer_corners([(0, 0), (5, 0), (5, 0), (5, 5)], cut=0.9, closed=False)
    say('a duplicated vertex does not fabricate a corner', len(c2) == 4,
        f'{len(c2)} points')
    c3 = chamfer_corners([(0, 0, 0), (6, 0, 3), (12, 0, 6), (12, 6, 6)],
                         cut=0.9, closed=False)
    mid = [p for p in c3 if abs(p[0] - 6) < 1.0]
    say('z is interpolated along the leg, not copied from the corner',
        len(mid) == 1 and abs(mid[0][2] - 3.0) < 1e-9, str(mid))
    spike = [(0, 0), (10, 0), (0.02, 0.3)]
    say('a near-reversal spike is canted by default (pipeline behaviour kept)',
        len(chamfer_corners(spike, cut=0.9, closed=False)) == 4)
    say('and collapsed when asked',
        len(chamfer_corners(spike, cut=0.9, closed=False, spike_turn=148.0)) == 2)
    c5, piers = chamfer_corners(sq, cut=0.9, want_piers=True)
    say('a 90-degree turn reports a quoined pier stop', len(piers) == 0,
        f'{len(piers)} piers at 90 deg (cantable, so none)')
    _, p6 = chamfer_corners([(0, 0), (10, 0), (9, 4)], cut=0.9, closed=False,
                            want_piers=True)
    say('a 104-degree turn reports one pier stop', len(p6) == 1, f'{len(p6)}')

    print('\nvectorise.py still calls through this module')
    import vectorise
    say('vectorise.chamfer now lives in ops_edges',
        vectorise.chamfer.__module__ == 'ops_edges'
        and vectorise.chamfer.__name__ == 'chamfer_corners',
        f'{vectorise.chamfer.__module__}.{vectorise.chamfer.__name__}')
    v = vectorise.chamfer(sq, closed=True)
    say('and returns 2D points to its 2D callers',
        len(v) == 8 and all(len(p) == 2 for p in v), f'{v[:2]}')

    print('\n' + ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


def _point_in(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
                inside = not inside
    return inside


if __name__ == '__main__':
    sys.exit(_selftest())
