"""SQLite database for menu items."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "menu.db"


def get_connection():
    """Return a database connection."""
    return sqlite3.connect(DB_PATH)


def _migrate_menu_items(conn):
    cur = conn.execute("PRAGMA table_info(menu_items)")
    cols = {row[1] for row in cur.fetchall()}
    if "options_json" not in cols:
        conn.execute("ALTER TABLE menu_items ADD COLUMN options_json TEXT")


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            image_path TEXT,
            options_json TEXT
        )
    """)
    _migrate_menu_items(conn)
    # Migrate existing categories from menu_items into categories table
    cur = conn.execute("SELECT DISTINCT category FROM menu_items")
    for row in cur.fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)",
            (row[0],),
        )
    # Ensure at least one category exists
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.execute("INSERT INTO categories (name) VALUES ('Menu')")
    conn.commit()
    conn.close()


def get_categories():
    """Return all categories sorted by name."""
    conn = get_connection()
    cur = conn.execute("SELECT name FROM categories ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def add_category(name: str) -> bool:
    """Add a category. Returns False if already exists."""
    name = name.strip()
    if not name:
        return False
    conn = get_connection()
    try:
        conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def _enrich_item_for_display(row: sqlite3.Row) -> dict:
    """Parse options_json into choice_groups and card price label."""
    d = {
        "id": row["id"],
        "title": row["title"],
        "price": row["price"],
        "description": row["description"] or "",
        "image_path": row["image_path"] or "",
        "choice_groups": [],
        "price_label": "",
        "has_choice_details": False,
    }
    raw = row["options_json"]
    if not raw:
        return d
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return d
    if isinstance(data, dict):
        d["price_label"] = (data.get("price_hint") or "").strip()
        tiers = data.get("tiers") or []
        d["choice_groups"] = tiers if isinstance(tiers, list) else []
        d["has_choice_details"] = len(d["choice_groups"]) > 0
    return d


def get_menu_by_category():
    """Return menu items grouped by category for template rendering."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, title, category, price, description, image_path, options_json "
        "FROM menu_items ORDER BY category, title"
    )
    rows = cur.fetchall()
    conn.close()

    categories = {}
    for row in rows:
        cat = row["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(_enrich_item_for_display(row))
    return [{"name": k, "items": v} for k, v in categories.items()]


def _truncate_description(text: str, max_words: int = 20) -> str:
    """Enforce description up to max_words."""
    if not text:
        return ""
    words = text.split()
    return " ".join(words[:max_words]) if len(words) > max_words else text


def add_item(
    title: str,
    category: str,
    price: float,
    description: str = "",
    image_path: str = "",
    options_json: str | None = None,
):
    """Add a menu item. Description is truncated to 20 words."""
    description = _truncate_description(description)
    conn = get_connection()
    conn.execute(
        "INSERT INTO menu_items (title, category, price, description, image_path, options_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, category, price, description, image_path, options_json),
    )
    conn.commit()
    conn.close()


def get_all_items():
    """Return all menu items with id for admin."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, title, category, price, description, image_path, options_json "
        "FROM menu_items ORDER BY category, title"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_item(item_id: int):
    """Get a single menu item by id."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, title, category, price, description, image_path, options_json FROM menu_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_item_for_display(item_id: int) -> dict | None:
    """Single item with parsed choice_groups for public menu / item sheet."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, title, category, price, description, image_path, options_json FROM menu_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    conn.close()
    return _enrich_item_for_display(row) if row else None


def update_item(
    item_id: int,
    title: str,
    category: str,
    price: float,
    description: str = "",
    image_path: str = "",
    options_json: str | None = None,
):
    """Update a menu item. Description is truncated to 20 words. Pass options_json=None to keep existing."""
    description = _truncate_description(description)
    conn = get_connection()
    if options_json is None:
        row = conn.execute(
            "SELECT options_json FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        options_json = row[0] if row else None
    conn.execute(
        "UPDATE menu_items SET title=?, category=?, price=?, description=?, image_path=?, options_json=? WHERE id=?",
        (title, category, price, description, image_path, options_json, item_id),
    )
    conn.commit()
    conn.close()


def delete_item(item_id: int):
    """Delete a menu item."""
    conn = get_connection()
    conn.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
