from pathlib import Path
import sys

from PIL import Image


source = Image.open(sys.argv[1]).convert("RGBA")
width, height = source.size
pixels = source.load()


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


for y in range(height):
    top = smooth(y / 38)
    bottom = smooth((height - y - 1) / 68)
    for x in range(width):
        edge = min(top, bottom, smooth(x / 52), smooth((width - x - 1) / 52))
        r, g, b, alpha = pixels[x, y]
        pixels[x, y] = (r, g, b, round(alpha * edge))

destination = Path(sys.argv[2]).resolve()
# The sidebar displays at most 300 CSS pixels tall. Keep a 2x thumbnail;
# original PNGs remain available for the full-size preview.
source.thumbnail((600, 600), Image.Resampling.LANCZOS)
source.save(destination, "WEBP", quality=88, method=6)
print(f"{destination}: {source.size}, {destination.stat().st_size} bytes")
