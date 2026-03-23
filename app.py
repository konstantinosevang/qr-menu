"""Flask menu server. Run: python app.py"""
import io
import os
import socket
import uuid
from pathlib import Path

import segno
from flask import Flask, Response, abort, redirect, render_template, request, url_for

from database import (
    add_category,
    add_item,
    delete_item,
    get_all_items,
    get_categories,
    get_item,
    get_item_for_display,
    get_menu_by_category,
    init_db,
    update_item,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4MB
UPLOAD_FOLDER = Path(__file__).parent / "static" / "images"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Quick patch: branded public path for QR / links (also served below).
MENU_PUBLIC_PATH = "/HarrisCreperie/menu"

# Ensure DB exists on startup
init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file) -> str | None:
    """Save uploaded file to static/images. Returns URL path or None."""
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex[:12]}.{ext}"
    path = UPLOAD_FOLDER / name
    file.save(path)
    return f"/static/images/{name}"


@app.route("/")
@app.route("/menu")
@app.route(MENU_PUBLIC_PATH)
def menu():
    return render_template("menu/menu.html", categories=get_menu_by_category())


@app.route("/item/<int:item_id>")
def item_detail(item_id: int):
    item = get_item_for_display(item_id)
    if not item:
        abort(404)
    partial = request.args.get("partial") == "1"
    return render_template("menu/item.html", item=item, partial=partial)


@app.route("/qr")
def menu_qr():
    """PNG QR code for the public menu URL (works behind Render / reverse proxies)."""
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    host = (request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip()
    base = f"{proto}://{host}".rstrip("/")
    menu_url = base + MENU_PUBLIC_PATH

    buf = io.BytesIO()
    segno.make(menu_url).save(buf, kind="png", scale=8)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png")


@app.route("/admin")
def admin():
    items = get_all_items()
    categories = get_categories()
    return render_template("admin.html", items=items, categories=categories)


@app.route("/admin/add", methods=["GET", "POST"])
def admin_add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip() or "Menu"
        try:
            price = float(request.form.get("price", 0))
        except ValueError:
            price = 0
        description = request.form.get("description", "").strip()
        image_path = request.form.get("image_path", "").strip()

        if request.files.get("image"):
            uploaded = save_uploaded_file(request.files["image"])
            if uploaded:
                image_path = uploaded

        if title:
            add_item(title, category, price, description, image_path)
        return redirect(url_for("admin"))
    return redirect(url_for("admin"))


@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    item = get_item(item_id)
    if not item:
        return redirect(url_for("admin"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip() or "Menu"
        try:
            price = float(request.form.get("price", 0))
        except ValueError:
            price = 0
        description = request.form.get("description", "").strip()
        image_path = request.form.get("image_path", "").strip()

        if request.files.get("image"):
            uploaded = save_uploaded_file(request.files["image"])
            if uploaded:
                image_path = uploaded

        if title:
            update_item(item_id, title, category, price, description, image_path)
        return redirect(url_for("admin"))

    items = get_all_items()
    categories = get_categories()
    return render_template("admin.html", items=items, categories=categories, edit_item=item)


@app.route("/admin/delete/<int:item_id>", methods=["POST"])
def admin_delete(item_id):
    delete_item(item_id)
    return redirect(url_for("admin"))


@app.route("/admin/category/add", methods=["POST"])
def admin_category_add():
    name = request.form.get("category_name", "").strip()
    if name:
        add_category(name)
    return redirect(request.referrer or url_for("admin"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()

    menu_url = f"http://{ip}:{port}/menu"
    admin_url = f"http://{ip}:{port}/admin"
    print(f"Menu: {menu_url}")
    print(f"Admin: {admin_url}")

    segno.make(menu_url).save("menu-qr.png", scale=8)
    segno.make(admin_url).save("admin-qr.png", scale=8)
    print("QR codes: menu-qr.png, admin-qr.png")

    app.run(host="0.0.0.0", port=port, use_reloader=False)
