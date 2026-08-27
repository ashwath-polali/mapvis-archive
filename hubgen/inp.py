"""Inpaint via the REST API directly — the MCP layer truncates inline images, so the
image rides in a plain python POST. Discovery mode first: a 422 from the API names the
exact missing/wrong fields and costs nothing; only an accepted body spends generations.

Fills wave23's two harbor doorways with solid wall. Windows are 128x128 crops; only the
masked region of each result is pasted back into the pristine painting.
"""
import base64, json, os, sys, time, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "gate-quality", "scripts"))
import pxl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W23 = os.path.join(HERE, "wave23")

DESC = ("a stone harbor wall of continuous sandstone masonry courses beneath a stone quay "
        "walkway, warm golden afternoon light, clean hand-painted pixel art")

# window, mask rect in window coords (x, y, w, h)
JOBS = [
    ("_inp-crop1.png", (42, 30, 36, 38), "fix1"),
    ("_inp-crop2.png", (45, 43, 30, 34), "fix2"),
]


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def mask_png(size, rect):
    from PIL import Image
    m = Image.new("L", size, 0)
    x, y, w, h = rect
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            m.putpixel((xx, yy), 255)
    import io
    buf = io.BytesIO()
    m.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def try_post(path, body):
    try:
        out = pxl.post(path, body)
        return ("ok", out)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf8", "ignore")[:1200]
        return ("http %d" % e.code, detail)


def main():
    from PIL import Image
    for crop_name, rect, out_name in JOBS:
        crop_path = os.path.join(W23, crop_name)
        im = Image.open(crop_path)
        body = {
            "description": DESC,
            "image_size": {"width": im.size[0], "height": im.size[1]},
            "inpainting_image": {"type": "base64", "base64": b64(crop_path)},
            "mask_image": {"type": "base64", "base64": mask_png(im.size, rect)},
        }
        st = out = None
        for ep in ("/v1/inpaint", "/v2/inpaint-image", "/v1/edit-image-inpaint",
                   "/v1/generate-image-inpaint", "/v2/inpaint"):
            st, out = try_post(ep, body)
            print(crop_name, ep, "->", st, flush=True)
            if st == "ok":
                break
            if not st.startswith("http 404"):
                print(out, flush=True)
                return
        if st != "ok":
            print("no endpoint found", flush=True)
            return
        p = os.path.join(W23, out_name + ".png")
        pxl.save_result(out, p)
        print("saved", p, flush=True)


if __name__ == "__main__":
    main()
