import sys, json
from PIL import Image
# usage: patch.py <file> <ops.json>   ops: [ [dx,dy,sx,sy,w,h,"name"], ... ]
f = sys.argv[1]
ops = json.load(open(sys.argv[2]))
im = Image.open(f).convert('RGBA')
for dx,dy,sx,sy,w,h,name in ops:
    region = im.crop((sx,sy,sx+w,sy+h))
    im.paste(region,(dx,dy))
    print(f"{name}: ({sx},{sy})->({dx},{dy}) {w}x{h}")
im.save(f)
