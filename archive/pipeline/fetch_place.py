"""
fetch_place.py - pull a REAL place as measurement. No model looks at anything.

This is MAPVIS phase A, and it deliberately does not ask any language model to
imagine a layout. The composition of the map comes from a real town that a real
history composed: its terrain, its street graph, its footprints, its quays.

Sources, all free and openly licensed:
  terrain    IGN RGE ALTI 1 m via the Geoplateforme WMS  (Etalab 2.0, France)
  vectors    OpenStreetMap via Overpass                  (ODbL)

    py fetch_place.py --place villefranche
"""
import argparse
import json
import os
import ssl
import urllib.parse
import urllib.request

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

UA = 'MAPVIS/0.1 (research; contact ashwathpolali@gmail.com)'

# Coastal towns with a strong single conceit and IGN LiDAR coverage.
# south/west/north/east
PLACES = {
    # steep amphitheatre wrapping a deep natural harbour, citadel on the point
    'villefranche': (43.6995, 7.3055, 43.7075, 7.3155),
    # limestone cliff town over a fjord-like marina
    'bonifacio':    (41.3830, 9.1520, 41.3920, 9.1650),
    # fishing harbour, castle on the water, terraced vineyard slope
    'collioure':    (42.5220, 3.0800, 42.5290, 3.0900),
    # calanque fishing port under a cliff
    'cassis':       (43.2110, 5.5330, 43.2170, 5.5430),
}

OVERPASS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]


def overpass(query):
    body = urllib.parse.urlencode({'data': query}).encode()
    last = None
    for url in OVERPASS:
        try:
            req = urllib.request.Request(url, data=body, headers={
                'User-Agent': UA,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': '*/*',
            })
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                return json.loads(r.read())
        except Exception as e:
            last = f'{url}: {type(e).__name__} {str(e)[:90]}'
            print('  retry ->', last)
    raise SystemExit('all overpass mirrors failed: ' + str(last))


def q_vectors(s, w, n, e):
    bb = f'{s},{w},{n},{e}'
    return f"""[out:json][timeout:180];
(
  way[building]({bb});
  relation[building]({bb});
  way[highway]({bb});
  way[natural=coastline]({bb});
  way[natural=cliff]({bb});
  way[man_made~"^(quay|pier|breakwater|groyne)$"]({bb});
  way[waterway=riverbank]({bb});
  way[natural=water]({bb});
  way[barrier~"^(retaining_wall|wall|city_wall)$"]({bb});
  way[historic~"^(citadel|castle|fort|city_gate)$"]({bb});
  way[amenity=place_of_worship]({bb});
  way[leisure=park]({bb});
  way[place=square]({bb});
  node[historic]({bb});
  node[amenity=place_of_worship]({bb});
);
(._;>;);
out body;"""


def wgs84_to_utm(lat, lon):
    """Plain WGS84 -> UTM forward. No pyproj dependency."""
    import math
    zone = int((lon + 180) / 6) + 1
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    la, lo = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    T = math.tan(la) ** 2
    C = ep2 * math.cos(la) ** 2
    A = math.cos(la) * (lo - lon0)
    M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * la
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * la)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * la)
             - (35 * e2 ** 3 / 3072) * math.sin(6 * la))
    k0 = 0.9996
    x = k0 * N * (A + (1 - T + C) * A ** 3 / 6
                  + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000.0
    y = k0 * (M + N * math.tan(la) * (A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
              + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720))
    if lat < 0:
        y += 10000000.0
    return x, y, zone


def fetch_terrain(s, w, n, e, out_png, px=1024):
    """IGN Geoplateforme WMS, RGE ALTI. The elevation layer renders as a greyscale
    image; we ask for a known bbox so metres-per-pixel is exact and stated."""
    params = {
        'SERVICE': 'WMS', 'VERSION': '1.3.0', 'REQUEST': 'GetMap',
        'LAYERS': 'ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW',
        'STYLES': '', 'CRS': 'CRS:84',
        'BBOX': f'{w},{s},{e},{n}',
        'WIDTH': str(px), 'HEIGHT': str(px),
        'FORMAT': 'image/png',
    }
    url = 'https://data.geopf.fr/wms-r/wms?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
        data = r.read()
    open(out_png, 'wb').write(data)
    return len(data)


def fetch_elevation_grid(s, w, n, e, out_json, nx=96):
    """Real metric elevation, sampled on a grid, from IGN's altimetry REST service.
    This is measured ground truth, not a shaded image."""
    lats, lons = [], []
    for j in range(nx):
        for i in range(nx):
            lats.append(s + (n - s) * (j + 0.5) / nx)
            lons.append(w + (e - w) * (i + 0.5) / nx)
    zs = []
    CH = 180                                     # service caps points per call
    for k in range(0, len(lats), CH):
        la = '|'.join(f'{v:.6f}' for v in lats[k:k + CH])
        lo = '|'.join(f'{v:.6f}' for v in lons[k:k + CH])
        url = ('https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json'
               f'?lon={lo}&lat={la}&resource=ign_rge_alti_wld&delimiter=|&zonly=true')
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
            zs += json.loads(r.read())['elevations']
        print(f'  elevation {min(k + CH, len(lats))}/{len(lats)}', end='\r')
    print()
    json.dump({'nx': nx, 'bbox': [s, w, n, e], 'z': zs}, open(out_json, 'w'))
    good = [v for v in zs if v is not None and v > -1000]
    return len(zs), (min(good), max(good)) if good else (None, None)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--place', default='villefranche', choices=sorted(PLACES))
    ap.add_argument('--out', default='place')
    a = ap.parse_args()
    s, w, n, e = PLACES[a.place]
    d = os.path.join(a.out, a.place)
    os.makedirs(d, exist_ok=True)
    print(f'[fetch] {a.place}  bbox S{s} W{w} N{n} E{e}')

    print('[fetch] vectors from OpenStreetMap ...')
    v = overpass(q_vectors(s, w, n, e))
    json.dump(v, open(os.path.join(d, 'osm.json'), 'w'))
    els = v['elements']
    ways = [x for x in els if x['type'] == 'way']
    bld = [x for x in ways if 'building' in x.get('tags', {})]
    hw = [x for x in ways if 'highway' in x.get('tags', {})]
    print(f'  {len(els)} elements, {len(ways)} ways, {len(bld)} buildings, {len(hw)} highways')

    print('[fetch] measured elevation from IGN RGE ALTI ...')
    cnt, rng = fetch_elevation_grid(s, w, n, e, os.path.join(d, 'elev.json'))
    print(f'  {cnt} samples, {rng[0]:.1f} m to {rng[1]:.1f} m')

    cx, cy, zone = wgs84_to_utm((s + n) / 2, (w + e) / 2)
    json.dump({'place': a.place, 'bbox': [s, w, n, e], 'utm_zone': zone,
               'origin_utm': [cx, cy]}, open(os.path.join(d, 'meta.json'), 'w'), indent=1)
    print(f'[fetch] UTM zone {zone}, origin {cx:.1f} {cy:.1f}  -> {d}')
