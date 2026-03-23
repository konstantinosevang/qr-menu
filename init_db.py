"""Initialize the database and optionally seed from menu_data.json."""
import json
from pathlib import Path

from database import add_item, init_db


def seed_from_json():
    """Migrate from menu_data.json if it exists and table is empty."""
    from database import get_connection

    conn = get_connection()
    if conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] > 0:
        conn.close()
        return
    conn.close()

    path = Path(__file__).parent / "menu_data.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for cat in data.get("categories", []):
        category_name = cat.get("name", "Menu")
        for item in cat.get("items", []):
            add_item(
                title=item.get("name", "Untitled"),
                category=category_name,
                price=float(item.get("price", 0)),
                description="",
                image_path=item.get("img", ""),
            )
    print(f"Seeded from {path}")


if __name__ == "__main__":
    init_db()
    seed_from_json()
    print("Database initialized.")
