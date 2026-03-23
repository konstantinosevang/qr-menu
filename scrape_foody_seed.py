"""
Fetch a Foody delivery shop menu (public catalog API), download images, seed SQLite.

CLI:
  python scrape_foody_seed.py --clear
  python scrape_foody_seed.py --url https://www.foody.com.cy/delivery/.../shop-name-12345

Programmatic: import_foody_menu(..., fetch_options=True) pulls tier choices via /v3/shops/catalog/product.
CLI: --no-options skips those calls (faster).

Requires: network access to foody.com.cy and apinew.foody.com.cy.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from database import DB_PATH, add_category, add_item, init_db

ROOT = Path(__file__).resolve().parent
STATIC_IMAGES = ROOT / "static" / "images"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"


def shop_id_from_url(url: str) -> str | None:
    m = re.search(r"-(\d{6,})\s*$", url.rstrip("/"))
    return m.group(1) if m else None


def fetch_shop_page(url: str) -> tuple[str, http.cookiejar.CookieJar]:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    return html, cj


def parse_user_sid(html: str) -> str:
    m = re.search(r'window\.app\.userSid\s*=\s*[\'"]([^\'"]+)[\'"]', html)
    if not m:
        raise ValueError("Could not find window.app.userSid in shop page")
    return m.group(1)


def fetch_catalog(page_url: str, shop_id: str, html: str, cj: http.cookiejar.CookieJar) -> dict:
    sid = parse_user_sid(html)
    ck = {c.name: c.value for c in cj}

    params = urllib.parse.urlencode(
        {
            "shop_id": shop_id,
            "version": 3,
            "latitude": 0,
            "longitude": 0,
            "category_slug": "",
        }
    )
    api_url = f"https://apinew.foody.com.cy/v3/shops/catalog?{params}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-core-platform": "web",
        "X-core-version": "1",
        "X-core-session-id": sid,
        "X-core-theme": "sonata-light",
        "X-core-perseus-client-id": ck.get("dhhPerseusGuestId", ""),
        "X-core-perseus-session-id": ck.get("dhhPerseusSessionId", ""),
        "Referer": page_url,
        "Origin": urllib.parse.urlparse(page_url).scheme + "://" + urllib.parse.urlparse(page_url).netloc,
        "Content-Type": "application/json",
        "Pragma": "no-cache",
    }
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(api_url, headers=headers)
    with opener.open(req, timeout=60) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    if payload.get("status") != "ok":
        raise RuntimeError(
            f"Catalog API error: {payload.get('error_code')} — {payload.get('message')}"
        )
    return payload["data"]


def needs_product_detail(item: dict) -> bool:
    return bool(
        item.get("has_variations")
        or item.get("has_options")
        or item.get("need_server_calculation")
    )


def fetch_product_detail(
    page_url: str,
    shop_id: str,
    item_code: str,
    html: str,
    cj: http.cookiejar.CookieJar,
) -> dict | None:
    """GET /v3/shops/catalog/product — returns product data or None."""
    if not item_code or not str(item_code).startswith("IT_"):
        return None
    sid = parse_user_sid(html)
    ck = {c.name: c.value for c in cj}
    params = urllib.parse.urlencode({"shop_id": shop_id, "item_code": item_code})
    api_url = f"https://apinew.foody.com.cy/v3/shops/catalog/product?{params}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-core-platform": "web",
        "X-core-version": "1",
        "X-core-session-id": sid,
        "X-core-theme": "sonata-light",
        "X-core-perseus-client-id": ck.get("dhhPerseusGuestId", ""),
        "X-core-perseus-session-id": ck.get("dhhPerseusSessionId", ""),
        "Referer": page_url,
        "Origin": urllib.parse.urlparse(page_url).scheme
        + "://"
        + urllib.parse.urlparse(page_url).netloc,
        "Content-Type": "application/json",
        "Pragma": "no-cache",
    }
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(api_url, headers=headers)
    try:
        with opener.open(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    if payload.get("status") != "ok":
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def build_options_payload(catalog_item: dict, product: dict | None) -> str | None:
    """JSON for menu_items.options_json: price_hint + tiers (choices / add-ons)."""
    hint = (catalog_item.get("calculated_price") or "").strip()
    tiers_raw = (product or {}).get("tiers") or []
    tiers_out: list[dict] = []

    for t in sorted(
        tiers_raw,
        key=lambda x: (x.get("order") is None, x.get("order", 0)),
    ):
        t_type = (t.get("type") or "checkbox").lower()
        raw_max = t.get("maximum_selections")
        if t_type == "radio":
            max_sel = 1
            min_sel = 1
        else:
            min_sel = 0
            max_sel = None if (raw_max == 0 or raw_max is None) else int(raw_max)

        opts_out = []
        for o in t.get("options") or []:
            if o.get("shortage"):
                continue
            name = (o.get("name") or "").strip()
            if not name:
                continue
            opts_out.append({
                "name": name,
                "price": float(o.get("price") or 0),
            })
        if not opts_out:
            continue

        tiers_out.append({
            "type": t_type,
            "name": (t.get("name") or "").strip() or "Options",
            "min": min_sel,
            "max": max_sel,
            "options": opts_out,
        })

    if tiers_out:
        return json.dumps({"price_hint": hint, "tiers": tiers_out}, ensure_ascii=False)
    if hint and needs_product_detail(catalog_item):
        return json.dumps({"price_hint": hint, "tiers": []}, ensure_ascii=False)
    return None


def _is_popular_category(cat: dict) -> bool:
    name = (cat.get("name") or "").strip().lower()
    tags = cat.get("tags") or []
    return name == "popular" or "popular-v3" in tags


def iter_menu_rows(categories: list, parent_label: str = "") -> list[tuple[str, dict]]:
    """Flatten category tree; skip synthetic Popular (duplicate items)."""
    rows: list[tuple[str, dict]] = []
    for cat in categories:
        if _is_popular_category(cat):
            sub = cat.get("categories") or []
            if sub:
                rows.extend(iter_menu_rows(sub, parent_label))
            continue

        name = (cat.get("name") or "Menu").strip() or "Menu"
        label = f"{parent_label} / {name}" if parent_label else name

        for item in cat.get("items") or []:
            if item.get("is_available", True):
                rows.append((label, item))

        sub = cat.get("categories") or []
        if sub:
            rows.extend(iter_menu_rows(sub, label))
    return rows


def dedupe_preserve_order(rows: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    seen: set[str] = set()
    out: list[tuple[str, dict]] = []
    for cat_name, item in rows:
        code = item.get("code") or f"id:{item.get('id')}"
        if code in seen:
            continue
        seen.add(code)
        out.append((cat_name, item))
    return out


def pick_image_url(item: dict) -> str | None:
    images = item.get("images") or {}
    for key in ("menu", "original", "featured"):
        u = images.get(key)
        if isinstance(u, str) and u.startswith("http"):
            return u
    return None


def extension_from_content_type(ct: str | None) -> str:
    if not ct:
        return "jpg"
    ct = ct.split(";")[0].strip().lower()
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "png" in ct:
        return "png"
    if "webp" in ct:
        return "webp"
    return "jpg"


def download_image(url: str, dest_without_ext: Path, pause_sec: float = 0.15) -> str | None:
    """Save image next to dest_without_ext with proper extension. Returns /static/images/... or None."""
    dest_without_ext.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            ext = extension_from_content_type(r.headers.get("Content-Type"))
            path = dest_without_ext.with_suffix("." + ext)
            path.write_bytes(r.read())
        time.sleep(pause_sec)
        return f"/static/images/{path.name}"
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def clear_menu_tables() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM menu_items")
    conn.execute("DELETE FROM categories")
    conn.commit()
    conn.close()


def is_foody_shop_url(url: str) -> bool:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    host = (p.netloc or "").lower()
    if "foody.com.cy" not in host:
        return False
    path = (p.path or "").lower()
    return "delivery" in path or "/menu/" in path


def import_foody_menu(
    page_url: str,
    *,
    shop_id: str | None = None,
    clear_existing: bool = True,
    download_images: bool = True,
    fetch_options: bool = True,
) -> dict[str, object]:
    """
    Fetch Foody catalog and seed the database.

    Returns a dict with either:
      {"ok": True, "shop_id", "items", "categories", "message"}
      {"ok": False, "message": "..."}
    """
    page_url = (page_url or "").strip()
    if not page_url:
        return {"ok": False, "message": "URL is required."}
    if not is_foody_shop_url(page_url):
        return {
            "ok": False,
            "message": "Enter a Foody Cyprus shop URL (e.g. …/delivery/…/shop-name-12345).",
        }

    resolved_id = (shop_id or "").strip() or None
    if not resolved_id:
        resolved_id = shop_id_from_url(page_url)
    if not resolved_id:
        return {
            "ok": False,
            "message": "Could not read shop id from the URL (expected …-SHOPID at the end). Use override below if needed.",
        }

    init_db()

    try:
        html, cj = fetch_shop_page(page_url)
        data = fetch_catalog(page_url, resolved_id, html, cj)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "message": f"HTTP error loading menu: {e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "message": f"Network error: {e.reason}"}
    except RuntimeError as e:
        return {"ok": False, "message": str(e)}
    except OSError as e:
        return {"ok": False, "message": f"IO error: {e}"}

    menu = data.get("menu") or {}
    categories = menu.get("categories") or []
    flat = dedupe_preserve_order(iter_menu_rows(categories))

    if clear_existing:
        clear_menu_tables()

    STATIC_IMAGES.mkdir(parents=True, exist_ok=True)

    category_names = sorted({c for c, _ in flat})
    for cname in category_names:
        add_category(cname)

    for cat_name, item in flat:
        title = (item.get("name") or item.get("title") or "Item").strip() or "Item"
        price = float(item.get("price") or item.get("full_price") or 0)
        desc = (item.get("description") or "").strip()
        code = (item.get("code") or "item").replace("/", "_")
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", code)[:80]

        image_path = ""
        if download_images:
            img_url = pick_image_url(item)
            if img_url:
                stem = STATIC_IMAGES / f"foody_{resolved_id}_{safe}"
                image_path = download_image(img_url, stem) or ""

        options_json = None
        if fetch_options and needs_product_detail(item):
            icode = item.get("code")
            prod = (
                fetch_product_detail(page_url, resolved_id, icode, html, cj)
                if icode
                else None
            )
            options_json = build_options_payload(item, prod)
            time.sleep(0.1)

        add_item(
            title,
            cat_name,
            price,
            description=desc,
            image_path=image_path,
            options_json=options_json,
        )

    msg = (
        f"Imported {len(flat)} items in {len(category_names)} categories "
        f"(shop {resolved_id})."
    )
    return {
        "ok": True,
        "shop_id": resolved_id,
        "items": len(flat),
        "categories": len(category_names),
        "message": msg,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Foody shop menu into menu.db")
    parser.add_argument(
        "--url",
        default="https://www.foody.com.cy/delivery/leykosia/haris-creperie-strovolos-2000448801",
        help="Shop delivery page URL",
    )
    parser.add_argument("--shop-id", default=None, help="Numeric shop id (default: parsed from URL)")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all menu_items and categories before seeding",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print counts only; no DB or image writes",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip downloading images",
    )
    parser.add_argument(
        "--no-options",
        action="store_true",
        help="Skip per-item API calls (tiers / make-your-own choices)",
    )
    args = parser.parse_args()

    shop_id = args.shop_id or shop_id_from_url(args.url)
    if not shop_id:
        raise SystemExit("Could not determine shop id; pass --shop-id")

    if args.dry_run:
        init_db()
        try:
            html, cj = fetch_shop_page(args.url)
            data = fetch_catalog(args.url, shop_id, html, cj)
        except Exception as e:
            raise SystemExit(str(e)) from e
        menu = data.get("menu") or {}
        categories = menu.get("categories") or []
        flat = dedupe_preserve_order(iter_menu_rows(categories))
        print(f"Shop {shop_id}: {len(flat)} items after dedupe (Popular skipped).")
        by_cat: dict[str, int] = {}
        for c, _ in flat:
            by_cat[c] = by_cat.get(c, 0) + 1
        for c, n in sorted(by_cat.items(), key=lambda x: x[0].lower()):
            print(f"  {c}: {n}")
        return

    result = import_foody_menu(
        args.url,
        shop_id=args.shop_id,
        clear_existing=args.clear,
        download_images=not args.no_images,
        fetch_options=not args.no_options,
    )
    if not result.get("ok"):
        raise SystemExit(result.get("message", "Import failed"))
    print(result["message"])


if __name__ == "__main__":
    main()
