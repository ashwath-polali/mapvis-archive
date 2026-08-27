"""MAPVIS KIT — the architecture layer library. Real construction, applied by rule.

Every failed map in this project was built from two of the eight layers that make a 3D map read:
the ground, and masses-as-boxes. The layers that actually carry the quality were never built at
all — what HOLDS the ground up, how you MOVE between levels, and where you PASS THROUGH.

This module is those layers, as parametric construction functions. None of them decides where
anything goes. Each one answers "given that a wall exists here, how is a wall actually built?" —
which is documented architecture, not composition, and is therefore something a machine can apply
everywhere a condition occurs.

    LAYER 2  retaining_wall   coursed, battered, with footing / string course / coping / buttresses
    LAYER 3  grand_stair      real riser+tread, a landing, cheek walls with raking coping
    LAYER 5  arch_gate        segmental arch, voussoirs, jambs, recessed reveal, dark interior
    LAYER 4  building_mass    base course, string course, oversailing eaves, pitched roof, gables
             parapet          a wall's crown where it fronts a drop

Units are METRES throughout. A person is 1.7 m. Every default below is a real building dimension:
risers near 180 mm, treads near 320 mm, coping oversail 250-300 mm, ashlar courses 400-600 mm.
"""
import math

# a person, for sanity-checking every proportion in here
CHAR_H = 1.7

# real construction constants
COURSE_H = 0.62          # one ashlar course. Chunkier than 'realistic': at game
                         # framing, fine coursing reads as corduroy stripes rather
                         # than as stone. Detail FREQUENCY matters as much as detail.
FOOTING_H = 0.80         # the plinth a wall stands on
FOOTING_OUT = 0.26       # how far the footing is proud of the wall face
STRING_H = 0.22          # a horizontal band partway up
STRING_OUT = 0.14
COPING_H = 0.34          # the cap that sheds water off the top
COPING_OUT = 0.28
BATTER = 1.0 / 14.0      # wall face leans back this much per unit of height
BUTTRESS_EVERY = 7.5     # metres between buttresses
BUTTRESS_W = 1.30
BUTTRESS_OUT = 0.85
RISER = 0.175            # stair
TREAD = 0.315
LANDING_LEN = 1.60
CHEEK_W = 0.55           # the solid wall flanking a flight
PARAPET_H = 1.05         # chest height on the safe side of a drop


class Mesh:
    """quad soup with per-face material slots. Deliberately dumb: geometry correctness lives in
    the construction functions, not in a mesh library."""

    def __init__(self):
        self.v = []
        self.f = []
        self.m = []

    def quad(self, a, b, c, d, mat=0):
        i = len(self.v)
        self.v += [a, b, c, d]
        self.f.append((i, i + 1, i + 2, i + 3))
        self.m.append(mat)

    def tri(self, a, b, c, mat=0):
        i = len(self.v)
        self.v += [a, b, c]
        self.f.append((i, i + 1, i + 2))
        self.m.append(mat)

    def box(self, cx, cy, z0, sx, sy, h, mat=0, inset_top=0.0):
        """axis-aligned box; inset_top tapers the top face inward (a batter, or a weathering)"""
        x0, x1 = cx - sx / 2, cx + sx / 2
        y0, y1 = cy - sy / 2, cy + sy / 2
        tx0, tx1 = x0 + inset_top, x1 - inset_top
        ty0, ty1 = y0 + inset_top, y1 - inset_top
        z1 = z0 + h
        self.quad((tx0, ty0, z1), (tx1, ty0, z1), (tx1, ty1, z1), (tx0, ty1, z1), mat)
        self.quad((x0, y0, z0), (x1, y0, z0), (tx1, ty0, z1), (tx0, ty0, z1), mat)
        self.quad((x1, y1, z0), (x0, y1, z0), (tx0, ty1, z1), (tx1, ty1, z1), mat)
        self.quad((x1, y0, z0), (x1, y1, z0), (tx1, ty1, z1), (tx1, ty0, z1), mat)
        self.quad((x0, y1, z0), (x0, y0, z0), (tx0, ty0, z1), (tx0, ty1, z1), mat)

    def extend(self, other):
        base = len(self.v)
        self.v += other.v
        self.f += [tuple(i + base for i in f) for f in other.f]
        self.m += other.m


def _lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# LAYER 2 — what holds the ground up
# ---------------------------------------------------------------------------
def retaining_wall(mesh, x0, x1, y, z_bot, z_top, mat=0, trim=1,
                   face=+1, buttresses=True, coping=True, string=True):
    """A wall running along X at depth `y`, retaining ground on the -face side.

    Built the way a real one is: a footing proud of the wall, courses that batter back as they
    rise, a string course partway up, a coping that oversails the top. Buttresses at intervals.
    `face` is which way the exposed face points in Y (+1 = toward +Y).

    This is the layer that carries most of what the eye reads in an Octopath terrace shot, and it
    is the layer that has never once been built in this project.
    """
    L = x1 - x0
    h = z_top - z_bot

    # footing: a proud plinth the wall stands on
    fy = y + face * (FOOTING_OUT / 2)
    mesh.box((x0 + x1) / 2, fy, z_bot, L, FOOTING_OUT, FOOTING_H, trim)

    # coursed body, battering back as it rises
    z = z_bot + FOOTING_H
    body_top = z_top - (COPING_H if coping else 0.0)
    while z < body_top - 1e-6:
        ch = min(COURSE_H, body_top - z)
        t0 = (z - z_bot) / max(h, 1e-6)
        t1 = (z + ch - z_bot) / max(h, 1e-6)
        # each course sits slightly further back than the one below it
        y0 = y + face * (-BATTER * h * t0)
        y1 = y + face * (-BATTER * h * t1)
        # alternate courses sit slightly proud, so each one casts its own shadow line instead
        # of the wall reading as one flat sheet with scratches on it
        proud = 0.055 if (int((z - z_bot) / COURSE_H) % 2 == 0) else 0.0
        y0p, y1p = y0 + face * proud, y1 + face * proud
        mesh.quad((x0, y0p, z), (x1, y0p, z), (x1, y1p, z + ch), (x0, y1p, z + ch), mat)
        # the reveal at the top of each course, which is what actually reads as coursing
        mesh.quad((x0, y1p, z + ch), (x1, y1p, z + ch), (x1, y1, z + ch), (x0, y1, z + ch), mat)
        z += ch

    # string course: a horizontal band, the strongest single shadow line on a tall wall
    if string and h > 3.0:
        sz = z_bot + h * 0.62
        st = (sz - z_bot) / h
        sy = y + face * (-BATTER * h * st + STRING_OUT / 2)
        mesh.box((x0 + x1) / 2, sy, sz, L, STRING_OUT, STRING_H, trim)

    # coping: the cap, oversailing both ways so it throws a shadow
    if coping:
        cy = y + face * (-BATTER * h + COPING_OUT / 2 - 0.06)
        mesh.box((x0 + x1) / 2, cy, z_top - COPING_H, L, COPING_OUT + 0.16, COPING_H, trim)

    # buttresses: battered piers, weathered on top
    if buttresses and L > BUTTRESS_EVERY * 1.4:
        n = max(1, int(L // BUTTRESS_EVERY))
        for i in range(1, n + 1):
            bx = x0 + L * i / (n + 1)
            bh = h * 0.74
            by = y + face * (BUTTRESS_OUT / 2)
            mesh.box(bx, by, z_bot, BUTTRESS_W, BUTTRESS_OUT, bh, mat,
                     inset_top=BUTTRESS_OUT * 0.16)
            # weathering: a sloped cap so water runs off
            mesh.box(bx, by, z_bot + bh, BUTTRESS_W * 0.92, BUTTRESS_OUT * 0.86, 0.30, trim,
                     inset_top=BUTTRESS_OUT * 0.30)


def parapet(mesh, x0, x1, y, z, mat=0, trim=1, h=PARAPET_H, thick=0.42):
    """the low wall on the safe side of a drop, with its own coping"""
    L = x1 - x0
    mesh.box((x0 + x1) / 2, y, z, L, thick, h - 0.12, mat)
    mesh.box((x0 + x1) / 2, y, z + h - 0.12, L, thick + 0.20, 0.12, trim)


# ---------------------------------------------------------------------------
# LAYER 3 — how you move between levels
# ---------------------------------------------------------------------------
def grand_stair(mesh, cx, y_bot, z_bot, z_top, width, mat=0, trim=1, landing=True):
    """A flight running in +Y from (cx, y_bot) at z_bot up to z_top.

    Real riser and tread, an optional landing at mid-height, solid cheek walls flanking it with a
    raking coping that follows the pitch. Returns the y the flight ends at, so a terrace can be
    built to meet it.
    """
    rise = z_top - z_bot
    n = max(2, int(round(rise / RISER)))
    r = rise / n
    steps_below = n // 2 if landing else n

    y = y_bot
    z = z_bot
    ys = [y]
    for i in range(n):
        mesh.box(cx, y + TREAD / 2, z, width, TREAD, r, mat)
        z += r
        y += TREAD
        if landing and i == steps_below - 1:
            mesh.box(cx, y + LANDING_LEN / 2, z - r, width, LANDING_LEN, r, mat)
            y += LANDING_LEN
        ys.append(y)

    # cheek walls: solid, raking, capped. They are what makes a flight read as built rather than
    # as a stack of slabs.
    for side in (-1, +1):
        wx = cx + side * (width / 2 + CHEEK_W / 2)
        yy = y_bot
        zz = z_bot
        for i in range(n):
            seg = TREAD
            if landing and i == steps_below:
                seg += LANDING_LEN
            mesh.box(wx, yy + seg / 2, z_bot - 0.4, CHEEK_W, seg,
                     (zz + r * 1.9) - (z_bot - 0.4), mat)
            mesh.box(wx, yy + seg / 2, zz + r * 1.9, CHEEK_W + 0.16, seg, 0.16, trim)
            zz += r
            yy += seg
    return y


# ---------------------------------------------------------------------------
# LAYER 5 — where you pass through
# ---------------------------------------------------------------------------
def arch_gate(mesh, cx, y, z_bot, width, height, depth, mat=0, trim=1, dark=2, segs=11):
    """A segmental-arched opening driven through a wall of thickness `depth`.

    Jambs stand slightly proud, the arch is built of real voussoirs, and the opening is RECESSED
    so the reveal throws a shadow. The interior is a separate dark material — an opening has to
    read as a hole, not as a painted rectangle.
    """
    hw = width / 2
    spring = z_bot + height * 0.62         # where the arch starts to turn
    rise = height - (spring - z_bot)
    R = (hw * hw + rise * rise) / (2 * rise)
    cz = spring + rise - R

    # the dark interior: floor, soffit, two cheeks
    y0, y1 = y - depth / 2, y + depth / 2
    mesh.quad((-hw + cx, y0, z_bot), (hw + cx, y0, z_bot),
              (hw + cx, y1, z_bot), (-hw + cx, y1, z_bot), dark)
    for side in (-1, +1):
        mesh.quad((cx + side * hw, y0, z_bot), (cx + side * hw, y1, z_bot),
                  (cx + side * hw, y1, spring), (cx + side * hw, y0, spring), dark)
    for i in range(segs):
        a0 = math.pi * i / segs
        a1 = math.pi * (i + 1) / segs
        p0 = (cx - R * math.cos(a0) * (hw / R if R else 1), cz + R * math.sin(a0))
        p1 = (cx - R * math.cos(a1) * (hw / R if R else 1), cz + R * math.sin(a1))
        x0 = cx + (p0[0] - cx)
        x1 = cx + (p1[0] - cx)
        z0 = max(p0[1], spring)
        z1 = max(p1[1], spring)
        mesh.quad((x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0), dark)

    # jambs, proud of the wall face
    for side in (-1, +1):
        mesh.box(cx + side * (hw + 0.26), y1 - 0.14, z_bot, 0.52, 0.28, spring - z_bot, trim)

    # voussoirs: the wedge stones of the arch ring, each one a separate block
    for i in range(segs):
        a = math.pi * (i + 0.5) / segs
        ux, uz = -math.cos(a), math.sin(a)
        px = cx + ux * hw
        pz = cz + uz * R
        if pz < spring - 0.05:
            continue
        w = (math.pi * hw) / segs * 1.16
        mesh.box(px + ux * 0.19, y1 - 0.13, pz + uz * 0.19 - 0.24, w, 0.30, 0.48, trim)


# ---------------------------------------------------------------------------
# LAYER 4 — the masses
# ---------------------------------------------------------------------------
def building_mass(mesh, cx, cy, z, sx, sy, wall_h, mat=0, trim=1, roof=3,
                  pitch=0.62, ridge_along_x=True):
    """A building, built like one: a base course proud of the wall, a string course, eaves that
    oversail, and a real pitched roof with gable ends. Not a prism."""
    BASE_H, BASE_OUT = 0.85, 0.22
    EAVE_H, EAVE_OUT = 0.34, 0.46

    mesh.box(cx, cy, z, sx + BASE_OUT * 2, sy + BASE_OUT * 2, BASE_H, trim)
    body_z = z + BASE_H
    body_h = wall_h - BASE_H - EAVE_H
    mesh.box(cx, cy, body_z, sx, sy, body_h, mat)
    mesh.box(cx, cy, body_z + body_h * 0.58, sx + 0.13, sy + 0.13, 0.17, trim)
    eave_z = body_z + body_h
    mesh.box(cx, cy, eave_z, sx + EAVE_OUT * 2, sy + EAVE_OUT * 2, EAVE_H, trim)

    # roof: two slopes meeting at a ridge, with real gable triangles at the ends
    rz = eave_z + EAVE_H
    ex, ey = sx / 2 + EAVE_OUT, sy / 2 + EAVE_OUT
    span = (sy if ridge_along_x else sx) / 2 + EAVE_OUT
    rh = span * pitch
    if ridge_along_x:
        mesh.quad((cx - ex, cy - ey, rz), (cx + ex, cy - ey, rz),
                  (cx + ex, cy, rz + rh), (cx - ex, cy, rz + rh), roof)
        mesh.quad((cx + ex, cy + ey, rz), (cx - ex, cy + ey, rz),
                  (cx - ex, cy, rz + rh), (cx + ex, cy, rz + rh), roof)
        for s in (-1, +1):
            mesh.tri((cx + s * ex, cy - ey, rz), (cx + s * ex, cy + ey, rz),
                     (cx + s * ex, cy, rz + rh), mat)
    else:
        mesh.quad((cx - ex, cy - ey, rz), (cx - ex, cy + ey, rz),
                  (cx, cy + ey, rz + rh), (cx, cy - ey, rz + rh), roof)
        mesh.quad((cx + ex, cy + ey, rz), (cx + ex, cy - ey, rz),
                  (cx, cy - ey, rz + rh), (cx, cy + ey, rz + rh), roof)
        for s in (-1, +1):
            mesh.tri((cx - ex, cy + s * ey, rz), (cx + ex, cy + s * ey, rz),
                     (cx, cy + s * ey, rz + rh), mat)
    return rz + rh


# ---------------------------------------------------------------------------
# LAYER 1 — the ground, as discrete planes
# ---------------------------------------------------------------------------
def slab(mesh, x0, x1, y0, y1, z, mat=0, drop_to=None):
    """a flat walkable plane, with a real vertical face dropped to `drop_to` on its -Y edge"""
    mesh.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), mat)
    if drop_to is not None and drop_to < z:
        mesh.quad((x0, y0, z), (x1, y0, z), (x1, y0, drop_to), (x0, y0, drop_to), mat)
