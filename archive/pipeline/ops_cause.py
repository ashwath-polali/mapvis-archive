"""
ops_cause.py - the cause registry. Makes L2 measurable and makes raw jitter unreachable.

Why this file exists:

CONSTRUCTION-THEORY L2 names CO-VISIBILITY OF CAUSE AND EFFECT IN ONE FRAME as the
mechanism that separates designed irregularity from noise. Its exact statement: every
element whose position, rotation or dimension deviates from its type's base module must
have its causing geometry projected into the SAME frame as the deviation, and at least
three undeviated instances of that same module must be legible in that same frame.

Nothing in the builder recorded WHY anything deviated. So frameaudit.py could report R1,
R3 and R4 and had to print NOT MEASURED for R2 - blind on the one law the theory says
carries the read. That blindness is not academic: 379 fully-justified placements were
rejected on sight because every reason lived in the solver and none was recoverable from
the image. A reason in a log is worth nothing.

Three records and one prohibition:

  Cause       named geometry - an outcrop, a spring line, an older tower, a fault plane,
              a reef gap - with an id, a world position and a bounding radius. It must be
              REAL geometry carrying its own name in the ID buffer, because "is the cause
              in frame" is answered from that buffer and from nothing else.
  Element     a registered instance of a prototype. Undeviated until something deviates it.
  Deviation   element id, prototype, the delta, and the responsible cause_id.

  deviate()   the ONLY sanctioned way to make anything irregular. A raw random offset
              cannot be expressed here, which is the whole point: L2's corollary is that
              unmotivated jitter is the failure the law forbids, not the fix it prescribes.

Two constraints that fall out of measurement rather than taste, and that callers must obey:

  1. THE BASE MODULE MUST BE AN ADDRESSABLE OBJECT. R2 counts undeviated siblings in the
     ID buffer. A wall merged into one mesh has no bays, so a kinked wall can never show
     three straight bays beside the kink. If a prototype can deviate, its instances are
     separate objects.
  2. ONE OBJECT NAME PER ELEMENT. Two elements sharing a name are one silhouette to the
     buffer and the audit cannot separate them. structural_check reports this as a defect
     rather than guessing.

Thresholds marked AUTHORED below are choices, not measurements. They are named, defaulted
and overridable so that a gate can be argued with instead of hidden.

No raycasting happens here. frameaudit.frustum_ids already produces the depth and
object-name buffers by ray, and a second raycaster would be a second source of truth.
This module also does not import bpy, so a registry can be written, read and checked
outside Blender.
"""
import json
import math
import os

CHAR = 1.7

# AUTHORED. A deviation larger than this is a relocation and wants its own placement, not
# a delta off a module. A deviation smaller than this is invisible at Octopath screen
# scale, so recording it buys a green gate and no read.
MAX_DEVIATION_CHAR = 3.0
MIN_DEVIATION_M = 0.02

# AUTHORED. "Legible in frame" on the audit buffer, which is ~96x54.
#
# These are counts of the LARGEST CONNECTED COMPONENT, not of matching cells anywhere, and
# that distinction is the whole reason this metric survived its own calibration. Measured:
# with a plain cell tally, pixel-shuffling the frame left R2 at 1/1 - identical - because a
# tally is permutation-invariant, which is the exact category error CONSTRUCTION-THEORY 1.1
# describes and section 6.2 says to discard a metric for. A cause smeared as 150 isolated
# cells is not recoverable by eye; the same 150 cells as one blob is an object. Requiring a
# component, and requiring it NEAR the deviation, makes the test sensitive to arrangement
# inside the frame and not merely to frame membership.
MIN_CAUSE_FRAC = 0.004
MIN_SIBLING_PX = 3
MIN_ELEMENT_PX = 3

# AUTHORED. How far the cause may sit from the deviation it explains, as a fraction of
# frame width. L2's mechanism is that the observer recovers the cause OF THIS deviation;
# a cause in the opposite corner is in frame and explains nothing.
MAX_CAUSE_GAP_FRAC = 0.35

# L2, literally: at least three undeviated instances of the same module in the same frame.
SIBLINGS_REQUIRED = 3

CAUSE_KINDS = ('outcrop', 'spring_line', 'older_structure', 'fault_plane', 'reef_gap',
               'waterline', 'bedding_parting', 'grade_break', 'boundary')

DEVIATION_KINDS = ('offset', 'rotate', 'dimension')


class CauseError(ValueError):
    """Raised when something tries to be irregular without a registered cause."""


def _largest_component(cells):
    """The biggest 4-connected run of cells. This is what makes an object an object, and
    what a pixel shuffle destroys while leaving a cell count untouched."""
    seen = set()
    best = set()
    for start in cells:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp = {start}
        while stack:
            r, c = stack.pop()
            for q in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if q in cells and q not in seen:
                    seen.add(q)
                    comp.add(q)
                    stack.append(q)
        if len(comp) > len(best):
            best = comp
    return best


def _blob_gap(a, b):
    """Separation between two cell blobs, in cells, via their bounding boxes. Zero when
    they touch or overlap."""
    if not a or not b:
        return float('inf')
    ar0, ar1 = min(r for r, _ in a), max(r for r, _ in a)
    ac0, ac1 = min(c for _, c in a), max(c for _, c in a)
    br0, br1 = min(r for r, _ in b), max(r for r, _ in b)
    bc0, bc1 = min(c for _, c in b), max(c for _, c in b)
    dr = max(0, ar0 - br1, br0 - ar1)
    dc = max(0, ac0 - bc1, bc0 - ac1)
    return math.hypot(dr, dc)


class Cause:
    __slots__ = ('id', 'kind', 'pos', 'radius', 'obj', 'note')

    def __init__(self, id, kind, pos, radius, obj, note=''):
        self.id = id
        self.kind = kind
        self.pos = tuple(float(v) for v in pos)
        self.radius = float(radius)
        self.obj = obj
        self.note = note

    def as_dict(self):
        return {'id': self.id, 'kind': self.kind, 'pos': list(self.pos),
                'radius': self.radius, 'obj': self.obj, 'note': self.note}


class Element:
    __slots__ = ('id', 'prototype', 'pos', 'rot', 'obj', 'deviated')

    def __init__(self, id, prototype, pos, rot, obj):
        self.id = id
        self.prototype = prototype
        self.pos = tuple(float(v) for v in pos)
        self.rot = float(rot)
        self.obj = obj
        self.deviated = False

    def as_dict(self):
        return {'id': self.id, 'prototype': self.prototype, 'pos': list(self.pos),
                'rot': self.rot, 'obj': self.obj, 'deviated': self.deviated}


class Deviation:
    __slots__ = ('element', 'prototype', 'kind', 'delta', 'cause')

    def __init__(self, element, prototype, kind, delta, cause):
        self.element = element
        self.prototype = prototype
        self.kind = kind
        self.delta = delta
        self.cause = cause

    def as_dict(self):
        return {'element': self.element, 'prototype': self.prototype, 'kind': self.kind,
                'delta': self.delta, 'cause': self.cause}

    def magnitude(self):
        if self.kind == 'offset':
            return math.sqrt(sum(v * v for v in self.delta))
        return abs(float(self.delta))


class Registry:
    """Causes, elements and the deviations that bind them. Deterministic, no randomness."""

    def __init__(self, scene=''):
        self.scene = scene
        self.causes = {}
        self.elements = {}
        self.deviations = []
        self._auto = {}

    # -------------------------------------------------------------- authoring
    def cause(self, id, kind, pos, radius, obj, note=''):
        if kind not in CAUSE_KINDS:
            raise CauseError(f"cause kind {kind!r} is not in the vocabulary {CAUSE_KINDS}")
        if id in self.causes:
            raise CauseError(f"cause id {id!r} already registered")
        if not obj:
            raise CauseError(
                f"cause {id!r} has no object name. A cause the ID buffer cannot see is a "
                f"reason in a solver, which is the failure L2 exists to catch.")
        if radius <= 0:
            raise CauseError(f"cause {id!r} radius must be positive")
        c = Cause(id, kind, pos, radius, obj, note)
        self.causes[id] = c
        return c

    def element(self, prototype, pos, obj, rot=0.0, id=None):
        if id is None:
            n = self._auto.get(prototype, 0)
            self._auto[prototype] = n + 1
            id = f'{prototype}#{n}'
        if id in self.elements:
            raise CauseError(f"element id {id!r} already registered")
        e = Element(id, prototype, pos, rot, obj)
        self.elements[id] = e
        return e

    def deviate(self, element, cause, kind, amount):
        """Move, turn or resize an element BECAUSE of a named cause. The only way in.

        Returns the element with its recorded state already updated, so the caller builds
        from `el.pos` / `el.rot` and the geometry cannot drift from the record.
        """
        el = element if isinstance(element, Element) else self.elements.get(element)
        if el is None or el.id not in self.elements:
            raise CauseError(f"deviate: element {element!r} is not registered")
        cid = cause.id if isinstance(cause, Cause) else cause
        if cid not in self.causes:
            raise CauseError(
                f"deviate: cause {cid!r} is not registered. Irregularity without a "
                f"registered cause is the jitter L2 forbids.")
        if kind not in DEVIATION_KINDS:
            raise CauseError(f"deviate: kind {kind!r} not in {DEVIATION_KINDS}")

        if kind == 'offset':
            d = tuple(float(v) for v in amount)
            if len(d) == 2:
                d = (d[0], d[1], 0.0)
            if len(d) != 3:
                raise CauseError("deviate offset wants (dx, dy) or (dx, dy, dz) in metres")
            mag = math.sqrt(sum(v * v for v in d))
            if mag < MIN_DEVIATION_M:
                raise CauseError(
                    f"deviate: offset {mag:.4f} m is below {MIN_DEVIATION_M} m and is not "
                    f"legible; a deviation nobody can see is a green gate, not a design")
            if mag > MAX_DEVIATION_CHAR * CHAR:
                raise CauseError(
                    f"deviate: offset {mag:.2f} m = {mag / CHAR:.2f} CHAR exceeds "
                    f"{MAX_DEVIATION_CHAR} CHAR; that is a relocation, place it instead")
            el.pos = (el.pos[0] + d[0], el.pos[1] + d[1], el.pos[2] + d[2])
            delta = list(d)
        elif kind == 'rotate':
            a = float(amount)
            if abs(a) < math.radians(1.0):
                raise CauseError(
                    f"deviate: rotation {math.degrees(a):.2f} deg is below 1 deg and reads "
                    f"as a modelling error rather than as a decision")
            el.rot += a
            delta = a
        else:
            a = float(amount)
            if abs(a) < MIN_DEVIATION_M:
                raise CauseError(f"deviate: dimension delta {a} m is below "
                                 f"{MIN_DEVIATION_M} m and is not legible")
            delta = a

        el.deviated = True
        self.deviations.append(Deviation(el.id, el.prototype, kind, delta, cid))
        return el

    # -------------------------------------------------------------- structure
    def siblings(self, prototype):
        return [e for e in self.elements.values()
                if e.prototype == prototype and not e.deviated]

    def structural_check(self):
        """What can be known without a camera. Returns (problems, notes).

        A problem here means R2 cannot pass in ANY frame, so it is worth more than a
        per-frame number: it says the map is unauditable rather than merely failing.
        """
        problems, notes = [], []
        by_obj = {}
        for e in self.elements.values():
            by_obj.setdefault(e.obj, []).append(e.id)
        for obj, ids in sorted(by_obj.items()):
            if len(ids) > 1:
                problems.append(
                    f"{len(ids)} elements share object {obj!r} ({', '.join(ids[:4])}"
                    f"{'...' if len(ids) > 4 else ''}); the ID buffer cannot separate them")
        for d in self.deviations:
            if d.element not in self.elements:
                problems.append(f"deviation on unknown element {d.element!r}")
            if d.cause not in self.causes:
                problems.append(f"deviation on {d.element!r} cites unknown cause {d.cause!r}")
        protos = {d.prototype for d in self.deviations}
        for p in sorted(protos):
            n = len(self.siblings(p))
            if n < SIBLINGS_REQUIRED:
                problems.append(
                    f"prototype {p!r} has a deviation but only {n} undeviated instances "
                    f"registered anywhere; L2 needs {SIBLINGS_REQUIRED} in frame, so this "
                    f"can never pass")
        for d in self.deviations:
            el = self.elements.get(d.element)
            c = self.causes.get(d.cause)
            if el is None or c is None:
                continue
            gap = math.dist(el.pos, c.pos) - c.radius
            notes.append(f"{d.element} <- {d.cause}: {d.kind} "
                         f"{d.magnitude():.2f}, cause surface {gap:.1f} m away")
        return problems, notes

    # -------------------------------------------------------------- the check
    def check_frame(self, names, min_cause_frac=MIN_CAUSE_FRAC,
                    min_sibling_px=MIN_SIBLING_PX, min_element_px=MIN_ELEMENT_PX,
                    max_gap_frac=MAX_CAUSE_GAP_FRAC):
        """R2 for one frame, from an object-name buffer.

        `names` is whatever frameaudit.frustum_ids returned: a 2D array (numpy or nested
        lists) of object names, '' where the ray hit nothing. Everything here is plain
        Python over that grid, so numpy stays optional and this module stays importable
        outside Blender.

        Three clauses, all of them arrangement-sensitive:
          the deviating element is legible as a blob      else `absent`, and absent does
                                                          NOT count against R2 - the law
                                                          is that a deviation is explained
                                                          where it is SEEN
          the cause is legible as a blob, near it         L2's projection clause, with the
                                                          proximity the machine form left
                                                          implicit
          >= 3 undeviated siblings are legible as blobs   L2's module clause, verbatim
        """
        grid = [[str(n) if n else '' for n in row] for row in names]
        h = len(grid)
        w = len(grid[0]) if h else 0
        total = h * w
        if not total:
            return {'rows': [], 'present': 0, 'passing': 0}
        cells = {}
        for r in range(h):
            for c in range(w):
                n = grid[r][c]
                if n:
                    cells.setdefault(n, set()).add((r, c))
        blob = {n: _largest_component(cs) for n, cs in cells.items()}

        rows = []
        for d in self.deviations:
            el = self.elements.get(d.element)
            c = self.causes.get(d.cause)
            el_blob = blob.get(el.obj, set()) if el else set()
            if el is None or c is None or len(el_blob) < min_element_px:
                rows.append({'element': d.element, 'cause': d.cause, 'kind': d.kind,
                             'absent': True, 'pass': None})
                continue
            cb = blob.get(c.obj, set())
            cause_frac = len(cb) / total
            gap = _blob_gap(el_blob, cb) / w if cb else 1.0
            cause_ok = cause_frac >= min_cause_frac and gap <= max_gap_frac
            sib = sum(1 for s in self.siblings(d.prototype)
                      if len(blob.get(s.obj, set())) >= min_sibling_px)
            sib_ok = sib >= SIBLINGS_REQUIRED
            rows.append({'element': d.element, 'cause': d.cause, 'kind': d.kind,
                         'absent': False, 'el_px': len(el_blob),
                         'cause_frac': round(cause_frac, 4), 'cause_gap': round(gap, 3),
                         'cause_ok': cause_ok, 'siblings': sib, 'siblings_ok': sib_ok,
                         'pass': bool(cause_ok and sib_ok)})
        present = [r for r in rows if not r['absent']]
        return {'rows': rows, 'present': len(present),
                'passing': sum(1 for r in present if r['pass'])}

    # -------------------------------------------------------------- transport
    def as_dict(self):
        return {'scene': self.scene, 'char': CHAR,
                'thresholds': {'min_cause_frac': MIN_CAUSE_FRAC,
                               'min_sibling_px': MIN_SIBLING_PX,
                               'max_cause_gap_frac': MAX_CAUSE_GAP_FRAC,
                               'siblings_required': SIBLINGS_REQUIRED},
                'causes': [c.as_dict() for c in self.causes.values()],
                'elements': [e.as_dict() for e in self.elements.values()],
                'deviations': [d.as_dict() for d in self.deviations]}

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w') as fh:
            json.dump(self.as_dict(), fh, indent=1)
        return path

    @classmethod
    def load(cls, path):
        with open(path) as fh:
            d = json.load(fh)
        r = cls(d.get('scene', ''))
        for c in d['causes']:
            r.causes[c['id']] = Cause(c['id'], c['kind'], c['pos'], c['radius'],
                                      c['obj'], c.get('note', ''))
        for e in d['elements']:
            el = Element(e['id'], e['prototype'], e['pos'], e['rot'], e['obj'])
            el.deviated = bool(e['deviated'])
            r.elements[el.id] = el
        for v in d['deviations']:
            r.deviations.append(Deviation(v['element'], v['prototype'], v['kind'],
                                          v['delta'], v['cause']))
        return r


def registry_path(scene, root=None):
    """Beside the geometry, named after the scene, so the audit can find it without argv."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, 'shots', f'causes-{scene}.json')


if __name__ == '__main__':
    # Self-test: the guards must actually fire. A check that never rejects is decoration.
    r = Registry('selftest')
    oc = r.cause('outcrop_a', 'outcrop', (6.0, 9.0, 1.4), 3.2, 'rock_outcrop_a')
    posts = [r.element('post', (x, 0.0, 0.0), f'post_{i}') for i, x in enumerate((0, 3, 6, 9))]
    bad = []
    for label, fn in (
            ('unregistered cause', lambda: r.deviate(posts[0], 'nope', 'offset', (0.4, 0))),
            ('unregistered element', lambda: r.deviate('ghost', oc, 'offset', (0.4, 0))),
            ('zero offset', lambda: r.deviate(posts[0], oc, 'offset', (0.0, 0.0))),
            ('offset past 3 CHAR', lambda: r.deviate(posts[0], oc, 'offset', (9.0, 0.0))),
            ('sub-degree rotation', lambda: r.deviate(posts[0], oc, 'rotate', 0.001)),
            ('bad kind', lambda: r.deviate(posts[0], oc, 'wiggle', 1.0)),
            ('cause with no object', lambda: r.cause('x', 'outcrop', (0, 0, 0), 1.0, None)),
            ('cause kind off-vocabulary', lambda: r.cause('y', 'vibes', (0, 0, 0), 1.0, 'g')),
    ):
        try:
            fn()
            bad.append(label)
        except CauseError:
            pass
    r.deviate(posts[0], oc, 'offset', (0.0, 1.1))
    probs, notes = r.structural_check()
    frame = [['rock_outcrop_a'] * 40 + ['post_0'] * 8 + ['post_1'] * 8 + ['post_2'] * 8
             + ['post_3'] * 8 + [''] * 24] * 20
    res = r.check_frame(frame)
    p = r.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots',
                            'causes-selftest.json'))
    back = Registry.load(p)
    print('guards that leaked:', bad or 'none')
    print('structural problems:', probs or 'none')
    for n in notes:
        print('  note:', n)
    print(f"frame: {res['passing']}/{res['present']} deviations explained in frame")
    print('round-trip identical:', back.as_dict() == r.as_dict())
