from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICO = ROOT / "assets" / "app_icon.ico"


def draw_icon(size: int) -> Image.Image:
    scale = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(points):
        return [(int(x * scale), int(y * scale)) for x, y in points]

    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(48 * scale), fill=(232, 248, 255, 255))

    outline = (14, 58, 70, 255)
    cyan = (89, 218, 238, 255)
    cyan2 = (57, 190, 220, 255)
    white = (255, 250, 244, 255)
    pink = (255, 178, 187, 255)
    blue = (53, 111, 255, 255)
    black = (24, 27, 30, 255)

    head = p([(36, 138), (58, 64), (101, 101), (132, 35), (159, 109), (206, 125), (191, 190), (132, 221), (68, 196)])
    d.polygon(head, fill=cyan, outline=outline)
    d.line(head + [head[0]], fill=outline, width=max(2, int(7 * scale)), joint="curve")

    muzzle = p([(78, 145), (126, 128), (203, 128), (220, 156), (181, 197), (105, 199), (63, 175)])
    d.polygon(muzzle, fill=white, outline=outline)
    d.line(muzzle + [muzzle[0]], fill=outline, width=max(2, int(6 * scale)), joint="curve")

    d.polygon(p([(65, 83), (82, 116), (58, 121)]), fill=pink)
    d.polygon(p([(131, 60), (147, 111), (119, 100)]), fill=pink)
    d.polygon(p([(91, 75), (113, 39), (116, 98)]), fill=black, outline=outline)
    d.arc([int(82 * scale), int(124 * scale), int(128 * scale), int(153 * scale)], 195, 345, fill=black, width=max(2, int(8 * scale)))
    d.rounded_rectangle([int(186 * scale), int(123 * scale), int(226 * scale), int(145 * scale)], radius=int(8 * scale), fill=black)

    paw = p([(175, 151), (226, 138), (249, 154), (239, 196), (190, 201), (170, 180)])
    d.polygon(paw, fill=cyan2, outline=outline)
    d.line(paw + [paw[0]], fill=outline, width=max(2, int(6 * scale)), joint="curve")

    d.polygon(p([(109, 76), (128, 87), (111, 95)]), fill=blue)
    d.polygon(p([(113, 166), (131, 159), (145, 174), (122, 178)]), fill=blue)
    d.polygon(p([(70, 199), (96, 211), (79, 222)]), fill=blue)
    d.ellipse([int(91 * scale), int(157 * scale), int(101 * scale), int(167 * scale)], fill=(255, 255, 255, 210))

    return img


def generate_icon() -> None:
    ICO.parent.mkdir(parents=True, exist_ok=True)
    base = draw_icon(256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(ICO, format="ICO", sizes=sizes)


generate_icon()
print(f"Wrote {ICO}")
