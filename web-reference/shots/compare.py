"""Side-by-side: reference (scaled to 1440x900) | OATH hero at 1440x900."""
from PIL import Image, ImageDraw
ref = Image.open("../hero.png").convert("RGB").resize((1440, 900), Image.LANCZOS)
mine = Image.open("oath-1440.png").convert("RGB")
out = Image.new("RGB", (2880 + 24, 900), (40, 40, 40))
out.paste(ref, (0, 0)); out.paste(mine, (1440 + 24, 0))
d = ImageDraw.Draw(out)
for y in (114, 341, 440, 620, 730):  # reference landmarks: dome top, badge, headline, CTA, stats
    d.line([(0, y), (2904, y)], fill=(255, 60, 60), width=1)
out.save("compare-1440.png")
out.resize((1452, 450), Image.LANCZOS).save("compare-1440-small.png")
print("ok")
