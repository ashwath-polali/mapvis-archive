from PIL import Image
im = Image.open('../cand-N_0.png').convert('RGBA')
W,H = im.size
px = im.load()
hits = []
for y in range(H):
    for x in range(W):
        r,g,b,a = px[x,y]
        if a>200 and r>235 and 110<g<215 and b<110:
            hits.append((x,y))
# cluster by proximity (dist <= 6)
clusters = []
for p in hits:
    placed = False
    for c in clusters:
        if any(abs(p[0]-q[0])<=6 and abs(p[1]-q[1])<=6 for q in c):
            c.append(p); placed=True; break
    if not placed:
        clusters.append([p])
# merge clusters
merged = True
while merged:
    merged = False
    for i in range(len(clusters)):
        for j in range(i+1,len(clusters)):
            if any(abs(p[0]-q[0])<=6 and abs(p[1]-q[1])<=6 for p in clusters[i] for q in clusters[j]):
                clusters[i]+=clusters[j]; del clusters[j]; merged=True; break
        if merged: break
for c in sorted(clusters, key=lambda c:(min(p[1] for p in c))):
    xs=[p[0] for p in c]; ys=[p[1] for p in c]
    print(f"n={len(c):4d}  x {min(xs)}-{max(xs)}  y {min(ys)}-{max(ys)}")
