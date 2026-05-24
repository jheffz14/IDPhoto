import os
import json
import uuid
import time
import io
import base64
from pathlib import Path
from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, send_file, abort)
from werkzeug.utils import secure_filename
from image_processor import IDPhotoProcessor

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
OUTPUT_DIR = BASE_DIR / "static" / "outputs"
CONFIG_FILE = DATA_DIR / "config.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


cfg = load_config()
app.secret_key = cfg["admin"].get("session_secret", "dev-secret")
app.config["MAX_CONTENT_LENGTH"] = cfg["app"].get("upload_max_mb", 20) * 1024 * 1024

ALLOWED = {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def is_admin():
    return session.get("admin_logged_in", False)


# ─── Public Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cfg = load_config()
    packages = {k: v for k, v in cfg["packages"].items() if v.get("enabled")}
    return render_template("index.html", cfg=cfg, packages=packages)


@app.route("/api/upload", methods=["POST"])
def upload():
    if "photo" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["photo"]
    if not f.filename or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file type"}), 400

    uid = uuid.uuid4().hex
    ext = f.filename.rsplit(".", 1)[1].lower()
    filename = f"{uid}.{ext}"
    path = UPLOAD_DIR / filename
    f.save(str(path))

    return jsonify({"upload_id": uid, "filename": filename,
                    "url": f"/static/uploads/{filename}"})


@app.route("/api/process", methods=["POST"])
def process():
    data = request.json or {}
    upload_id = data.get("upload_id")
    package_id = data.get("package_id")
    replace_bg = data.get("replace_background", False)
    bg_color = data.get("background_color", "#ffffff")

    if not upload_id or not package_id:
        return jsonify({"error": "Missing upload_id or package_id"}), 400

    cfg = load_config()

    # find upload file
    matches = list(UPLOAD_DIR.glob(f"{upload_id}.*"))
    if not matches:
        return jsonify({"error": "Upload not found"}), 404
    upload_path = matches[0]

    package = cfg["packages"].get(package_id)
    if not package:
        return jsonify({"error": "Package not found"}), 404

    try:
        processor = IDPhotoProcessor(cfg)
        result_id = uuid.uuid4().hex
        output_path = OUTPUT_DIR / f"{result_id}.png"

        processor.process(
            input_path=str(upload_path),
            output_path=str(output_path),
            package=package,
            replace_background=replace_bg,
            bg_color=bg_color
        )

        return jsonify({
            "result_id": result_id,
            "preview_url": f"/static/outputs/{result_id}.png",
            "download_base": result_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download/<result_id>/<fmt>")
def download(result_id, fmt):
    if fmt not in ("png", "jpeg", "pdf"):
        abort(400)
    safe = result_id.replace("/", "").replace(".", "")
    src = OUTPUT_DIR / f"{safe}.png"
    if not src.exists():
        abort(404)

    cfg = load_config()
    processor = IDPhotoProcessor(cfg)

    if fmt == "png":
        return send_file(str(src), mimetype="image/png",
                         as_attachment=True, download_name="id_photo_layout.png")
    elif fmt == "jpeg":
        buf = processor.convert_to_jpeg(str(src))
        return send_file(buf, mimetype="image/jpeg",
                         as_attachment=True, download_name="id_photo_layout.jpg")
    elif fmt == "pdf":
        buf = processor.convert_to_pdf(str(src))
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True, download_name="id_photo_layout.pdf")


@app.route("/api/config/public")
def public_config():
    cfg = load_config()
    return jsonify({
        "photo_sizes": cfg["photo_sizes"],
        "packages": {k: v for k, v in cfg["packages"].items() if v.get("enabled")},
        "paper_sizes": cfg["paper_sizes"]
    })


# ─── Admin Auth ───────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    cfg = load_config()
    if request.method == "POST":
        data = request.json or {}
        if (data.get("username") == cfg["admin"]["username"] and
                data.get("password") == cfg["admin"]["password"]):
            session["admin_logged_in"] = True
            return jsonify({"success": True})
        return jsonify({"error": "Invalid credentials"}), 401
    return render_template("admin_login.html", cfg=cfg)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ─── Admin Panel ──────────────────────────────────────────────────────────────

@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("admin_login"))
    cfg = load_config()
    return render_template("admin.html", cfg=cfg)


# ─── Admin API ────────────────────────────────────────────────────────────────

def require_admin(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/api/admin/config", methods=["GET"])
@require_admin
def get_config():
    return jsonify(load_config())


@app.route("/api/admin/config", methods=["POST"])
@require_admin
def update_config():
    cfg = load_config()
    data = request.json or {}
    # Merge top-level app settings (non-admin)
    for key in ("app", "paper_sizes"):
        if key in data:
            cfg[key] = data[key]
    save_config(cfg)
    return jsonify({"success": True})


# Photo sizes CRUD
@app.route("/api/admin/photo_sizes", methods=["POST"])
@require_admin
def create_photo_size():
    cfg = load_config()
    data = request.json or {}
    sid = data.get("id") or uuid.uuid4().hex[:8]
    cfg["photo_sizes"][sid] = {
        "name": data.get("name", "New Size"),
        "width_mm": float(data.get("width_mm", 35)),
        "height_mm": float(data.get("height_mm", 45)),
        "background_color": data.get("background_color", "#ffffff"),
        "enabled": data.get("enabled", True)
    }
    save_config(cfg)
    return jsonify({"success": True, "id": sid})


@app.route("/api/admin/photo_sizes/<sid>", methods=["PUT"])
@require_admin
def update_photo_size(sid):
    cfg = load_config()
    if sid not in cfg["photo_sizes"]:
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    cfg["photo_sizes"][sid].update({
        "name": data.get("name", cfg["photo_sizes"][sid]["name"]),
        "width_mm": float(data.get("width_mm", cfg["photo_sizes"][sid]["width_mm"])),
        "height_mm": float(data.get("height_mm", cfg["photo_sizes"][sid]["height_mm"])),
        "background_color": data.get("background_color", cfg["photo_sizes"][sid]["background_color"]),
        "enabled": data.get("enabled", cfg["photo_sizes"][sid]["enabled"])
    })
    save_config(cfg)
    return jsonify({"success": True})


@app.route("/api/admin/photo_sizes/<sid>", methods=["DELETE"])
@require_admin
def delete_photo_size(sid):
    cfg = load_config()
    if sid not in cfg["photo_sizes"]:
        return jsonify({"error": "Not found"}), 404
    del cfg["photo_sizes"][sid]
    save_config(cfg)
    return jsonify({"success": True})


# Packages CRUD
@app.route("/api/admin/packages", methods=["POST"])
@require_admin
def create_package():
    cfg = load_config()
    data = request.json or {}
    pid = data.get("id") or f"pkg_{uuid.uuid4().hex[:6]}"
    cfg["packages"][pid] = {
        "name": data.get("name", "New Package"),
        "description": data.get("description", ""),
        "enabled": data.get("enabled", True),
        "items": data.get("items", []),
        "paper_size": data.get("paper_size", "a4"),
        "orientation": data.get("orientation", "portrait"),
        "margin_mm": float(data.get("margin_mm", 5)),
        "spacing_mm": float(data.get("spacing_mm", 3)),
        "show_cut_lines": data.get("show_cut_lines", True),
        "background_color": data.get("background_color", "#ffffff")
    }
    save_config(cfg)
    return jsonify({"success": True, "id": pid})


@app.route("/api/admin/packages/<pid>", methods=["PUT"])
@require_admin
def update_package(pid):
    cfg = load_config()
    if pid not in cfg["packages"]:
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    pkg = cfg["packages"][pid]
    pkg.update({
        "name": data.get("name", pkg["name"]),
        "description": data.get("description", pkg.get("description", "")),
        "enabled": data.get("enabled", pkg["enabled"]),
        "items": data.get("items", pkg["items"]),
        "paper_size": data.get("paper_size", pkg["paper_size"]),
        "orientation": data.get("orientation", pkg.get("orientation", "portrait")),
        "margin_mm": float(data.get("margin_mm", pkg["margin_mm"])),
        "spacing_mm": float(data.get("spacing_mm", pkg["spacing_mm"])),
        "show_cut_lines": data.get("show_cut_lines", pkg["show_cut_lines"]),
        "background_color": data.get("background_color", pkg.get("background_color", "#ffffff"))
    })
    save_config(cfg)
    return jsonify({"success": True})


@app.route("/api/admin/packages/<pid>", methods=["DELETE"])
@require_admin
def delete_package(pid):
    cfg = load_config()
    if pid not in cfg["packages"]:
        return jsonify({"error": "Not found"}), 404
    del cfg["packages"][pid]
    save_config(cfg)
    return jsonify({"success": True})


@app.route("/api/admin/change_password", methods=["POST"])
@require_admin
def change_password():
    cfg = load_config()
    data = request.json or {}
    if data.get("current") != cfg["admin"]["password"]:
        return jsonify({"error": "Current password incorrect"}), 400
    cfg["admin"]["password"] = data.get("new_password", cfg["admin"]["password"])
    save_config(cfg)
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
