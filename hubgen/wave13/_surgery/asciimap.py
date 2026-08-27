from PIL import Image
import sys
x0,y0,x1,y1 = map(int, sys.argv[1:5])
im = Image.open('../cand-N_0.png').convert('RGBA')
px = im.load()
print("    " + "".join(str((x//10)%10) for x in range(x0,x1)))
print("    " + "".join(str(x%10) for x in range(x0,x1)))
for y in range(y0,y1):
    row = ""
    for x in range(x0,x1):
        r,g,b,a = px[x,y]
        v = (r+g+b)/3
        if a < 200: c='.'
        elif r>195 and g>150 and v>160: c=' '   # bright sunlit tan
        elif v>120 and r>140: c='-'              # mid tan / lit shade
        elif v>70: c='+'                          # shadow brown
        else: c='#'                               # dark outline/deep shadow
        row += c
    print(f"{y:3d} {row}")
