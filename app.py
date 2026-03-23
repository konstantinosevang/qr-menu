"""Flask menu server. Run: python app.py"""
import threading
import uuid
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from database import (
    add_category,
    add_item,
    delete_item,
    get_all_items,
    get_categories,
    get_item,
    get_menu_by_category,
    init_db,
    update_item,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4MB
UPLOAD_FOLDER = Path(__file__).parent / "static" / "images"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

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
def menu():
    return render_template("index.html", categories=get_menu_by_category())


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


def _prompt_yes_no(question: str) -> bool:
    while True:
        answer = input(f"{question} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please type y or n.")


if __name__ == "__main__":
    port = 5000
    use_ngrok = _prompt_yes_no("Use ngrok for a public URL")

    def run_flask():
        app.run(host="0.0.0.0", port=port, use_reloader=False)

    thread = threading.Thread(target=run_flask, daemon=True)
    thread.start()

    import time
    time.sleep(2)

    menu_url = None
    admin_url = None

    if use_ngrok:
        try:
            from pyngrok import ngrok

            tunnel = ngrok.connect(port)
            base_url = tunnel.public_url.rstrip("/")
            menu_url = f"{base_url}/menu"
            admin_url = f"{base_url}/admin"
            print(f"Menu (public): {menu_url}")
            print(f"Admin: {admin_url}")
        except Exception as e:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            menu_url = f"http://{ip}:{port}/menu"
            admin_url = f"http://{ip}:{port}/admin"
            print(f"ngrok failed ({e}), using local IP")
            print(f"Menu (local): {menu_url}")
            print(f"Admin: {admin_url}")
            print("Tip: Set NGROK_AUTH_TOKEN for public access (sign up at ngrok.com)")
    else:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        menu_url = f"http://{ip}:{port}/menu"
        admin_url = f"http://{ip}:{port}/admin"
        print("Skipping ngrok.")
        print(f"Menu (local): {menu_url}")
        print(f"Admin: {admin_url}")

    import segno
    segno.make(menu_url).save("menu-qr.png", scale=8)
    segno.make(admin_url).save("admin-qr.png", scale=8)
    print(f"QR: menu-qr.png, admin-qr.png")

    thread.join()
