"""The spray judged where it lives: on the hub's own waterfall, at game scale."""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HUB = r"C:\Users\ashcy\MAPVIS-next\public\hub-final.png"
SPRAY = os.path.join(HERE, "spray")

BASE_AT = (223, 170)     # where the left fall lands
MOUTH_AT = (222, 116)    # just under the left panther's jaw


def sheet(scale: float, name: str):
    hub = Image.open(HUB).convert("RGBA")
    shots = []
    for i in (0, 2, 4, 6):
        stage = hub.copy()
        for src, at in ((f"spray-base-{i}.png", BASE_AT), (f"spray-mouth-{i}.png", MOUTH_AT)):
            fr = Image.open(os.path.join(SPRAY, src)).convert("RGBA")
            p = fr.resize((max(1, round(fr.width * scale)), max(1, round(fr.height * scale))), Image.NEAREST)
            stage.alpha_composite(p, (at[0] - p.width // 2, at[1] - p.height))
        crop = stage.crop((BASE_AT[0] - 55, 88, BASE_AT[0] + 55, 196))
        shots.append(crop)
    out = Image.new("RGBA", (shots[0].width * len(shots) + 6 * len(shots), shots[0].height), (18, 18, 22, 255))
    for i, s in enumerate(shots):
        out.alpha_composite(s, (i * (s.width + 6), 0))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save(os.path.join(HERE, name))
    print("wrote", name)


if __name__ == "__main__":
    sheet(1.0, "_spray-on-fall.png")
