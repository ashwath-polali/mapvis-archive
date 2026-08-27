import sys
from PIL import Image
# usage: crop.py <src> <x> <y> <w> <h> <scale> <out>
src, x, y, w, h, scale, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
im = Image.open(src).convert('RGBA')
c = im.crop((x, y, x+w, y+h))
c = c.resize((c.width*scale, c.height*scale), Image.NEAREST)
c.save(out)
print(f"{out} <- ({x},{y}) {w}x{h} @{scale}x")
