"""The hub island GROUND PLAN, drawn as a flat color-block sketch in the iso view.

This is the geometry authority the prompts never had: text cannot direct the generator
geometrically (measured), an init image can (measured). Every walkable surface here is broad,
connected and empty BY CONSTRUCTION: quay ring, central plaza, one wide avenue to ONE portal,
stair bands, one dock finger. Houses flank the sides and never touch the way. The generator's
only job later is to paint cand-1's style over this fixed skeleton (pixflux init, low-mid
strength). The sketch is an INPUT for the generator, not art.
"""
import os
from PIL import Image, ImageDraw

W, H = 400, 224
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan-sketch.png")

SEA = (47, 125, 134)
QUAY = (196, 168, 128)       # main walk stone
PLAZA = (214, 188, 148)      # lighter open plaza
AVENUE = (222, 198, 158)     # the way to the portal
TERRACE = (182, 152, 112)    # upper terrace ground
WALLF = (140, 110, 82)       # terrace/quay wall faces
VOLC = (122, 88, 64)         # volcano rock
MOSS = (96, 128, 70)         # green slopes
HEAD = (150, 142, 130)       # panther head stone
PORTAL = (34, 26, 30)        # the one doorway
HOUSE = (158, 92, 62)        # house blocks
ROOF = (188, 108, 66)
SAND = (222, 202, 150)
DOCK = (134, 96, 60)
LIGHT = (210, 206, 196)
STALL = (196, 70, 60)

im = Image.new("RGBA", (W, H), SEA + (255,))
d = ImageDraw.Draw(im)


def poly(pts, c):
    d.polygon(pts, fill=c)


def rect(x0, y0, x1, y1, c):
    d.rectangle([x0, y0, x1, y1], fill=c)


# ---- the island: corner-facing iso diamond, asymmetric like cand-1 ----
# lower quay platform (the big walkable ring)
poly([(52, 150), (200, 96), (368, 152), (204, 214)], QUAY)
# quay wall face south
poly([(52, 150), (204, 214), (204, 222), (52, 158)], WALLF)
poly([(204, 214), (368, 152), (368, 160), (204, 222)], WALLF)

# mid terrace
poly([(96, 122), (204, 82), (322, 124), (206, 168)], TERRACE)
poly([(96, 122), (206, 168), (206, 176), (96, 130)], WALLF)
poly([(206, 168), (322, 124), (322, 132), (206, 176)], WALLF)

# central plaza (open, lighter)
poly([(142, 130), (206, 106), (276, 132), (208, 158)], PLAZA)

# ---- volcano mass with moss slopes, heads, ONE portal ----
poly([(150, 78), (204, 12), (262, 80), (206, 100)], VOLC)          # cone
poly([(150, 78), (172, 40), (188, 78)], MOSS)                       # moss left slope
poly([(262, 80), (238, 38), (222, 78)], MOSS)                       # moss right slope
d.ellipse([138, 52, 172, 84], fill=HEAD)                            # left panther head
d.ellipse([240, 52, 274, 84], fill=HEAD)                            # right panther head
rect(192, 66, 222, 96, PORTAL)                                      # THE portal
d.rectangle([188, 62, 226, 68], fill=HEAD)                          # portal lintel

# ---- the avenue: portal -> plaza -> quay -> dock, one straight wide way ----
poly([(192, 96), (222, 96), (232, 158), (182, 158)], AVENUE)        # portal to plaza
poly([(190, 158), (226, 158), (238, 200), (178, 200)], AVENUE)      # plaza to quay edge
rect(182, 100, 232, 106, PLAZA)                                     # stair band top
rect(178, 164, 238, 170, PLAZA)                                     # stair band low

# ---- ONE dock finger + lighthouse on a curl ----
rect(196, 200, 224, 220, DOCK)                                      # dock into the sea
poly([(320, 160), (352, 148), (372, 158), (344, 172)], QUAY)        # breakwater curl
d.ellipse([352, 138, 366, 158], fill=LIGHT)                         # lighthouse

# ---- houses flanking the SIDES only, never the avenue ----
for x, y in [(108, 108), (128, 100), (150, 92), (96, 132), (118, 140),
             (252, 92), (274, 100), (296, 110), (300, 132), (280, 142)]:
    rect(x, y, x + 18, y + 12, HOUSE)
    rect(x - 1, y - 4, x + 19, y + 2, ROOF)

# ---- one stall beside the plaza, off the way ----
rect(154, 136, 168, 146, STALL)
rect(153, 133, 169, 137, (230, 226, 214))

# ---- barrels tight against walls (dots) ----
for x, y in [(120, 152), (126, 154), (286, 148), (292, 150), (240, 180), (246, 182)]:
    d.ellipse([x, y, x + 5, y + 5], fill=(120, 82, 48))

# ---- beach cove lower-left ----
poly([(52, 150), (96, 168), (120, 196), (76, 200), (48, 172)], SAND)

im.save(OUT)
print("plan sketch:", OUT, im.size)
