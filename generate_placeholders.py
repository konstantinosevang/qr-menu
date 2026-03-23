"""Generate placeholder images for all menu items and update DB."""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from database import get_all_items, update_item

IMAGES_DIR = Path(__file__).parent / "static" / "images"
SIZE = 200

FONT_PATHS = [
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def slugify(text: str) -> str:
    return re.sub(r"[^\w\-]", "-", text.lower()).strip("-")


def get_font():
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, 24)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_placeholder(title: str, filepath: Path) -> None:
    """Create a placeholder image with the item title."""
    img = Image.new("RGB", (SIZE, SIZE), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    font = get_font()

    # Word-wrap title (max ~15 chars per line)
    words = title.split()
    lines = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 <= 12:
            current = f"{current} {w}".strip() if current else w
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    lines = lines[:3]  # Max 3 lines

    # Center text block
    line_height = 28
    total_h = line_height * len(lines)
    y = (SIZE - total_h) // 2

    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
        except (AttributeError, TypeError):
            tw = len(line) * 8  # Approximate for default font
        x = (SIZE - tw) // 2
        draw.text((x, y), line, fill=(80, 80, 80), font=font)
        y += line_height

    img.save(filepath, "PNG")


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    items = get_all_items()

    for item in items:
        filename = f"{item['id']}-{slugify(item['title'])}.png"
        filepath = IMAGES_DIR / filename
        generate_placeholder(item["title"], filepath)
        image_path = f"/static/images/{filename}"
        update_item(
            item["id"],
            item["title"],
            item["category"],
            item["price"],
            item["description"] or "",
            image_path,
        )
        print(f"  {item['title']} -> {filename}")

    print(f"Generated {len(items)} placeholder images.")


if __name__ == "__main__":
    main()
