from flask import Flask, request, render_template, send_file, session, redirect, jsonify, url_for
from PIL import Image, ImageOps
from io import BytesIO
from dotenv import load_dotenv
import requests
import uuid
import datetime
import utils
load_dotenv()
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import os

app = Flask(__name__)
app.secret_key = "SANUWAR_PHOTO_SECRET"


REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


@app.before_request
def check_maintenance():
    config = utils.load_config()
    maintenance = config.get("maintenance", {})
    if maintenance.get("enabled"):
        # Allow admin routes
        if request.path.startswith("/admin") or request.path.startswith("/api/admin") or request.path == "/api/maintenance/status":
            return
        
        # If API request
        if request.path.startswith("/api/") or request.path == "/process":
            return jsonify({"error": "maintenance", "message": maintenance.get("message")}), 503
        
        # If HTML request
        return render_template("maintenance.html", message=maintenance.get("message")), 503

@app.route("/api/maintenance/status")
def maintenance_status():
    config = utils.load_config()
    return jsonify({"enabled": config.get("maintenance", {}).get("enabled", False)})


# --- ADMIN ROUTES ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin")
@login_required
def admin_dashboard():
    return render_template("admin.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        username = data.get("username")
        password = data.get("password")
        
        config = utils.load_config()
        admin_conf = config.get("admin", {})
        
        if username == admin_conf.get("username") and utils.check_password(password, admin_conf.get("password_hash")):
            session["admin_logged_in"] = True
            return jsonify({"success": True})
        return jsonify({"error": "Invalid credentials"}), 401
    
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

@app.route("/api/admin/dashboard")
@login_required
def api_admin_dashboard():
    try:
        config = utils.load_config()
        keys = config.get("api_keys", [])
        active_key = next((k for k in keys if k.get("active")), None)
        
        return jsonify({
            "total_keys": len(keys),
            "active_key_label": active_key.get("label") if active_key else "None",
            "maintenance_enabled": config.get("maintenance", {}).get("enabled", False)
        })
    except Exception as e:
        print(f"Error in api_admin_dashboard: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/keys", methods=["GET", "POST"])
@login_required
def api_admin_keys():
    try:
        config = utils.load_config()
        if request.method == "GET":
            keys = config.get("api_keys", [])
            # Mask keys
            masked_keys = []
            for k in keys:
                km = k.copy()
                kn = km["key"]
                km["key"] = kn[:6] + "..." + kn[-4:] if len(kn) > 10 else "***"
                masked_keys.append(km)
            return jsonify(masked_keys)
            
        if request.method == "POST":
            data = request.json
            new_key = {
                "id": str(uuid.uuid4()),
                "service": data.get("service", "remove_bg"),
                "key": data.get("key"),
                "label": data.get("label", "New Key"),
                "active": data.get("active", False),
                "added_at": datetime.datetime.now().isoformat(),
                "usage_count": 0,
                "last_failed": None
            }
            config.setdefault("api_keys", []).append(new_key)
            utils.save_config(config)
            return jsonify({"success": True, "key": new_key})
    except Exception as e:
        print(f"Error in api_admin_keys: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/keys/<key_id>/activate", methods=["POST"])
@login_required
def api_admin_activate_key(key_id):
    try:
        config = utils.load_config()
        keys = config.get("api_keys", [])
        
        # Find key to see its service
        target_key = next((k for k in keys if k.get("id") == key_id), None)
        if not target_key:
            return jsonify({"error": "key_not_found"}), 404
            
        service = target_key.get("service")
        
        # Deactivate others in same service, activate this one
        for k in keys:
            if k.get("service") == service:
                k["active"] = (k.get("id") == key_id)
                if k["active"]:
                    k["last_failed"] = None # Reset fail state on manual activation
                    
        utils.save_config(config)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in api_admin_activate_key: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/keys/<key_id>", methods=["DELETE"])
@login_required
def api_admin_delete_key(key_id):
    try:
        config = utils.load_config()
        keys = config.get("api_keys", [])
        config["api_keys"] = [k for k in keys if k.get("id") != key_id]
        utils.save_config(config)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in api_admin_delete_key: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/maintenance", methods=["POST"])
@login_required
def api_admin_maintenance():
    try:
        data = request.json
        config = utils.load_config()
        maintenance = config.setdefault("maintenance", {})
        maintenance["enabled"] = bool(data.get("enabled"))
        if "message" in data:
            maintenance["message"] = data.get("message")
        utils.save_config(config)
        return jsonify({"success": True, "maintenance": maintenance})
    except Exception as e:
        print(f"Error in api_admin_maintenance: {e}")
        return jsonify({"error": "Internal server error"}), 500


# --- COUNTDOWN ROUTES ---

@app.route("/api/countdowns", methods=["GET"])
def api_get_countdowns_public():
    """Public endpoint — returns only enabled countdowns for the home page."""
    config = utils.load_config()
    all_cds = config.get("countdowns", [])
    enabled = [c for c in all_cds if c.get("enabled")]
    return jsonify(enabled)

@app.route("/api/admin/countdowns", methods=["GET"])
@login_required
def api_admin_get_countdowns():
    config = utils.load_config()
    return jsonify(config.get("countdowns", []))

@app.route("/api/admin/countdowns", methods=["POST"])
@login_required
def api_admin_add_countdown():
    try:
        data = request.json
        if not data.get("title") or not data.get("target_date"):
            return jsonify({"error": "title and target_date are required"}), 400
        config = utils.load_config()
        new_cd = {
            "id": str(uuid.uuid4()),
            "title": data["title"],
            "target_date": data["target_date"],
            "enabled": bool(data.get("enabled", True)),
            "created_at": datetime.datetime.now().isoformat()
        }
        config.setdefault("countdowns", []).append(new_cd)
        utils.save_config(config)
        return jsonify({"success": True, "countdown": new_cd})
    except Exception as e:
        print(f"Error adding countdown: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/countdowns/<cd_id>", methods=["PUT"])
@login_required
def api_admin_update_countdown(cd_id):
    try:
        data = request.json
        config = utils.load_config()
        countdowns = config.get("countdowns", [])
        cd = next((c for c in countdowns if c["id"] == cd_id), None)
        if not cd:
            return jsonify({"error": "not_found"}), 404
        if "title" in data:
            cd["title"] = data["title"]
        if "target_date" in data:
            cd["target_date"] = data["target_date"]
        if "enabled" in data:
            cd["enabled"] = bool(data["enabled"])
        utils.save_config(config)
        return jsonify({"success": True, "countdown": cd})
    except Exception as e:
        print(f"Error updating countdown: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/countdowns/<cd_id>", methods=["DELETE"])
@login_required
def api_admin_delete_countdown(cd_id):
    try:
        config = utils.load_config()
        config["countdowns"] = [c for c in config.get("countdowns", []) if c["id"] != cd_id]
        utils.save_config(config)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting countdown: {e}")
        return jsonify({"error": "Internal server error"}), 500


# --- WIDGET ROUTES (Home Screen Builder) ---

@app.route("/api/widgets", methods=["GET"])
def api_widgets_public():
    """Public — returns all enabled widgets sorted by order."""
    config = utils.load_config()
    widgets = [w for w in config.get("widgets", []) if w.get("enabled")]
    widgets.sort(key=lambda x: x.get("order", 0))
    return jsonify(widgets)

@app.route("/api/admin/widgets", methods=["GET"])
@login_required
def api_admin_widgets_get():
    config = utils.load_config()
    widgets = config.get("widgets", [])
    widgets.sort(key=lambda x: x.get("order", 0))
    return jsonify(widgets)

@app.route("/api/admin/widgets", methods=["POST"])
@login_required
def api_admin_widgets_add():
    try:
        data = request.json
        if not data.get("type"):
            return jsonify({"error": "type is required"}), 400
        config = utils.load_config()
        widgets = config.get("widgets", [])
        new_widget = {
            "id": str(uuid.uuid4()),
            "type": data["type"],
            "enabled": bool(data.get("enabled", True)),
            "order": len(widgets),
            "data": data.get("data", {}),
            "created_at": datetime.datetime.now().isoformat()
        }
        widgets.append(new_widget)
        config["widgets"] = widgets
        utils.save_config(config)
        return jsonify({"success": True, "widget": new_widget})
    except Exception as e:
        print(f"Error adding widget: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/upload", methods=["POST"])
@login_required
def api_admin_upload():
    try:
        import cloudinary.uploader
        
        # Check if JSON payload (Base64)
        if request.is_json:
            data = request.json
            if "file" not in data:
                return jsonify({"error": "No file provided in JSON"}), 400
            file_data = data["file"]
            upload_result = cloudinary.uploader.upload(file_data, resource_type="auto")
        else:
            # Fallback to Multipart
            if "image" not in request.files:
                return jsonify({"error": "No image file provided"}), 400
            file = request.files["image"]
            if file.filename == "":
                return jsonify({"error": "No selected file"}), 400
            upload_result = cloudinary.uploader.upload(file, resource_type="auto")
            
        secure_url = upload_result.get("secure_url")
        return jsonify({"success": True, "url": secure_url})
    except Exception as e:
        print(f"Widget Image Upload Error: {e}")
        return jsonify({"error": "Cloudinary upload failed: " + str(e)}), 500

@app.route("/api/admin/widgets/<widget_id>", methods=["PUT"])
@login_required
def api_admin_widgets_update(widget_id):
    try:
        data = request.json
        config = utils.load_config()
        widgets = config.get("widgets", [])
        w = next((x for x in widgets if x["id"] == widget_id), None)
        if not w:
            return jsonify({"error": "not_found"}), 404
        if "enabled" in data: w["enabled"] = bool(data["enabled"])
        if "order" in data:   w["order"]   = int(data["order"])
        if "data" in data:    w["data"]    = data["data"]
        config["widgets"] = widgets
        utils.save_config(config)
        return jsonify({"success": True, "widget": w})
    except Exception as e:
        print(f"Error updating widget: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/widgets/<widget_id>", methods=["DELETE"])
@login_required
def api_admin_widgets_delete(widget_id):
    try:
        config = utils.load_config()
        config["widgets"] = [w for w in config.get("widgets", []) if w["id"] != widget_id]
        utils.save_config(config)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting widget: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/admin/widgets/reorder", methods=["POST"])
@login_required
def api_admin_widgets_reorder():
    try:
        order = request.json.get("order", [])
        config = utils.load_config()
        widgets = config.get("widgets", [])
        id_to_pos = {wid: idx for idx, wid in enumerate(order)}
        for w in widgets:
            if w["id"] in id_to_pos:
                w["order"] = id_to_pos[w["id"]]
        config["widgets"] = widgets
        utils.save_config(config)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def sync_store_apps_to_github():
    try:
        import os, shutil, requests, base64
        # Always sync local copy first
        shutil.copy("data/downloads.json", "github-pages-app/data.json")
        
        # Github Sync
        github_pat  = os.getenv("GITHUB_PAT")
        github_user = os.getenv("GITHUB_USER")
        github_repo = os.getenv("GITHUB_REPO")
        
        if not github_pat or not github_user or not github_repo:
            print("Github Sync skipped: Missing GITHUB_PAT, GITHUB_USER or GITHUB_REPO in .env")
            return
            
        with open("data/downloads.json", "r") as f:
            content = f.read()
        
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"token {github_pat}",
            "Accept": "application/vnd.github.v3+json"
        }

        def push_file(path):
            url = f"https://api.github.com/repos/{github_user}/{github_repo}/contents/{path}"
            get_res = requests.get(url, headers=headers)
            sha = get_res.json().get("sha") if get_res.status_code == 200 else None
            payload = {
                "message": "Auto-sync store apps from Admin Panel",
                "content": encoded
            }
            if sha:
                payload["sha"] = sha
            put_res = requests.put(url, headers=headers, json=payload)
            if put_res.status_code in [200, 201]:
                print(f"✅ Synced to GitHub: {path}")
            else:
                print(f"❌ Failed to sync {path}: {put_res.text[:200]}")

        # Push to both locations so GitHub Pages always gets updated
        push_file("data/downloads.json")
        push_file("github-pages-app/data.json")

    except Exception as e:
        print(f"Error syncing to github: {e}")


@app.route("/api/admin/store-apps", methods=["GET", "POST"])
@login_required
def create_store_app():
    import json
    # GET — return all items
    if request.method == "GET":
        try:
            with open("data/downloads.json", "r") as f:
                items = json.load(f)
            return jsonify(items)
        except FileNotFoundError:
            return jsonify([])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    try:
        data = request.json
        try:
            with open("data/downloads.json", "r") as f:
                items = json.load(f)
        except FileNotFoundError:
            items = []
            
        new_app = {
            "id": f"app_{uuid.uuid4().hex[:8]}",
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "link": data.get("link", ""),
            "image": data.get("image", ""),
            "category": data.get("category", "Apps"),
            "version": data.get("version", ""),
            "is_album": data.get("is_album", False),
            "album_files": data.get("album_files", [])
        }
        
        items.insert(0, new_app) # Add to top
        with open("data/downloads.json", "w") as f:
            json.dump(items, f, indent=2)
            
        sync_store_apps_to_github()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/store-apps/<app_id>", methods=["PUT"])
@login_required
def update_store_app(app_id):
    import json
    try:
        data = request.json
        with open("data/downloads.json", "r") as f:
            items = json.load(f)
            
        for idx, item in enumerate(items):
            if item.get("id") == app_id:
                items[idx]["title"] = data.get("title", item["title"])
                items[idx]["description"] = data.get("description", item["description"])
                items[idx]["link"] = data.get("link", item["link"])
                items[idx]["image"] = data.get("image", item["image"])
                items[idx]["category"] = data.get("category", item["category"])
                items[idx]["version"] = data.get("version", item.get("version", ""))
                if "is_album" in data:
                    items[idx]["is_album"] = data["is_album"]
                if "album_files" in data:
                    items[idx]["album_files"] = data["album_files"]
                break
                
        with open("data/downloads.json", "w") as f:
            json.dump(items, f, indent=2)
            
        sync_store_apps_to_github()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/store-apps/<app_id>", methods=["DELETE"])
@login_required
def delete_store_app(app_id):
    import json
    try:
        with open("data/downloads.json", "r") as f:
            items = json.load(f)
        
        # Find the item to delete
        item_to_delete = next((x for x in items if x.get("id") == app_id), None)
        if not item_to_delete:
            return jsonify({"error": "Item not found"}), 404

        # Optionally destroy from Cloudinary
        try:
            import cloudinary.uploader
            links_to_delete = []
            if item_to_delete.get("is_album"):
                for af in item_to_delete.get("album_files", []):
                    links_to_delete.append(af.get("link", ""))
            else:
                links_to_delete.append(item_to_delete.get("link", ""))
                
            for link in links_to_delete:
                if link and "res.cloudinary.com" in link:
                    # Extract public_id from URL
                    parts = link.split("/upload/")
                    if len(parts) > 1:
                        public_id = parts[1].rsplit(".", 1)[0]
                        # Strip any transformations
                        public_id = public_id.replace("fl_attachment/", "")
                        cloudinary.uploader.destroy(public_id, resource_type="auto")
        except Exception as cloud_err:
            print(f"Cloudinary delete warning (non-fatal): {cloud_err}")

        # Remove from list
        items = [x for x in items if x.get("id") != app_id]
        
        with open("data/downloads.json", "w") as f:
            json.dump(items, f, indent=2)
            
        sync_store_apps_to_github()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/widgets/<widget_id>/vote", methods=["POST"])
def api_widget_vote(widget_id):

    """Session-protected poll voting."""
    try:
        data = request.json
        option_id = data.get("option_id")
        if not option_id:
            return jsonify({"error": "option_id required"}), 400
        voted_key = f"voted_{widget_id}"
        if session.get(voted_key):
            return jsonify({"error": "already_voted"}), 403
        config = utils.load_config()
        widgets = config.get("widgets", [])
        w = next((x for x in widgets if x["id"] == widget_id and x["type"] == "poll"), None)
        if not w:
            return jsonify({"error": "poll_not_found"}), 404
        options = w["data"].get("options", [])
        opt = next((o for o in options if o["id"] == option_id), None)
        if not opt:
            return jsonify({"error": "option_not_found"}), 404
        opt["votes"] = opt.get("votes", 0) + 1
        config["widgets"] = widgets
        utils.save_config(config)
        session[voted_key] = True
        return jsonify({"success": True, "options": options})
    except Exception as e:
        print(f"Error voting: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/downloads")
def downloads():
    return render_template("downloads.html")

@app.route("/api/downloads_data")
def api_downloads_data():
    import json
    try:
        with open("data/downloads.json", "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print(f"Error loading downloads data: {e}")
        return jsonify([])


@app.route("/sitemap.xml")
def sitemap():
    import datetime
    from flask import Response
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{request.host_url.rstrip('/')}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/robots.txt")
def robots():
    from flask import Response
    txt = f"User-agent: *\nAllow: /\nSitemap: {request.host_url.rstrip('/')}/sitemap.xml\n"
    return Response(txt, mimetype="text/plain")


def hex_to_rgb(hex_color):
    """Convert a hex color string (e.g. '#3B82F6') to an (R, G, B) tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (255, 255, 255)  # Fallback to white
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def process_single_image(input_image_bytes, bg_color="#FFFFFF"):
    """Remove background, enhance, and return a ready-to-paste passport PIL image.

    Args:
        input_image_bytes: Raw image bytes for the upload.
        bg_color: Hex color string for the background (default white).
    """
    bg_rgb = hex_to_rgb(bg_color)

    # Step 1: Background removal via remove.bg (called ONCE per image)
    
    # Try with active key, if it fails due to quota, rotate and try next.
    max_retries = 2
    response = None
    
    for attempt in range(max_retries):
        active_key_info = utils.get_active_api_key("remove_bg")
        # If no active key defined in config, fallback to env variable
        current_api_key = active_key_info.get("key") if active_key_info else REMOVE_BG_API_KEY
        
        if not current_api_key:
            raise ValueError("No remove.bg API key available. Please add one in the Admin Panel.")

        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": input_image_bytes},
            data={"size": "auto"},
            headers={"X-Api-Key": current_api_key},
        )

        if response.status_code == 200:
            # Success, increment usage count
            if active_key_info:
                config = utils.load_config()
                for k in config.get("api_keys", []):
                    if k.get("id") == active_key_info.get("id"):
                        k["usage_count"] = k.get("usage_count", 0) + 1
                        utils.save_config(config)
                        break
            break # Exit retry loop
            
        else:
            # Handle failure
            try:
                error_info = response.json()
                error_code = error_info.get("errors", [{}])[0].get("code", "unknown_error")
                error_title = error_info.get("errors", [{}])[0].get("title", "")
            except Exception:
                error_code = "unknown_error"
                error_title = response.text
                
            # If rate limited, out of credits, or unauthorized, try to rotate
            if response.status_code in [402, 403, 429] or "insufficient_credits" in error_code.lower() or "quota" in error_title.lower():
                if active_key_info and attempt < max_retries - 1:
                    print(f"API Key {active_key_info.get('label')} failed (Code: {response.status_code}). Rotating...")
                    next_key = utils.rotate_api_key(active_key_info.get("id"), "remove_bg")
                    if next_key:
                        continue # Retry with next key
                
            raise ValueError(f"bg_removal_failed:{error_code}:{response.status_code}")

    if not response or response.status_code != 200:
         raise ValueError(f"bg_removal_failed:unknown_error")

    bg_removed = BytesIO(response.content)
    img = Image.open(bg_removed)

    # Ensure RGBA so we can extract the alpha mask
    if img.mode not in ("RGBA", "LA"):
        img = img.convert("RGBA")

    # Step 2: Save the alpha mask BEFORE Cloudinary (gen_restore strips transparency)
    alpha_mask = img.split()[-1]

    # Flatten to white for Cloudinary enhancement (gives best quality results)
    flat_img = Image.new("RGB", img.size, (255, 255, 255))
    flat_img.paste(img, mask=alpha_mask)

    # Step 3: Upload flattened image to Cloudinary for AI enhancement
    buffer = BytesIO()
    flat_img.save(buffer, format="PNG")
    buffer.seek(0)
    upload_result = cloudinary.uploader.upload(buffer, resource_type="image")
    image_url = upload_result.get("secure_url")
    public_id = upload_result.get("public_id")

    if not image_url:
        raise ValueError("cloudinary_upload_failed")

    # Step 4: Enhance via Cloudinary AI
    enhanced_url = cloudinary.utils.cloudinary_url(
        public_id,
        transformation=[
            {"effect": "gen_restore"},
            {"quality": "100"},
            {"fetch_format": "png"},
        ],
    )[0]

    enhanced_img_data = requests.get(enhanced_url).content
    enhanced_img = Image.open(BytesIO(enhanced_img_data)).convert("RGB")

    # Step 5: Resize alpha mask to match enhanced image (in case of size mismatch)
    if alpha_mask.size != enhanced_img.size:
        alpha_mask = alpha_mask.resize(enhanced_img.size, Image.LANCZOS)

    # Step 6: Composite the enhanced subject onto the user-selected background color
    background = Image.new("RGB", enhanced_img.size, bg_rgb)
    background.paste(enhanced_img, mask=alpha_mask)
    passport_img = background

    return passport_img


@app.route("/process", methods=["POST"])
def process():
    print("==== /process endpoint hit ====")

    if not REMOVE_BG_API_KEY:
        return {"error": "Remove.bg API Key missing. Please provide .env or setup keys."}, 500
    if not CLOUDINARY_CLOUD_NAME:
        return {"error": "Cloudinary details missing. Please provide .env or setup keys."}, 500

    try:
        # Layout settings
        # Higher DPI scaling for maximum quality (600 DPI instead of 300 DPI)
        scale = 2
        passport_width = int(request.form.get("width", 390)) * scale
        passport_height = int(request.form.get("height", 480)) * scale
        border = int(request.form.get("border", 2)) * scale
        spacing = int(request.form.get("spacing", 10)) * scale
        bg_color = request.form.get("bg_color", "#FFFFFF")  # Background color from UI
        margin_x = 10 * scale
        margin_y = 10 * scale
        horizontal_gap = 10 * scale
        a4_w, a4_h = 2480 * scale, 3508 * scale

        # Collect images and their copy counts
        images_data = []

        # Multi-image mode
        i = 0
        while f"image_{i}" in request.files:
            file = request.files[f"image_{i}"]
            copies = int(request.form.get(f"copies_{i}", 6))
            images_data.append((file.read(), copies))
            i += 1

        # Fallback to single image mode
        if not images_data and "image" in request.files:
            file = request.files["image"]
            copies = int(request.form.get("copies", 6))
            images_data.append((file.read(), copies))

        if not images_data:
            return "No image uploaded", 400

        print(f"DEBUG: Processing {len(images_data)} image(s)")

        # Process all images
        passport_images = []
        for idx, (img_bytes, copies) in enumerate(images_data):
            print(f"DEBUG: Processing image {idx + 1} with {copies} copies")
            try:
                img = process_single_image(img_bytes, bg_color=bg_color)
                img = img.resize((passport_width, passport_height), Image.LANCZOS)
                img = ImageOps.expand(img, border=border, fill="black")
                passport_images.append((img, copies))
            except ValueError as e:
                err_str = str(e)
                if "410" in err_str or "face" in err_str.lower():
                    return {"error": "face_detection_failed"}, 410
                elif "429" in err_str or "quota" in err_str.lower() or "402" in err_str or "insufficient_credits" in err_str.lower():
                    return {"error": "quota_exceeded"}, 429
                elif "403" in err_str or "auth_failed" in err_str.lower():
                    return {"error": "API Key is invalid or unauthorized."}, 500
                else:
                    print(f"ERROR processing image {idx}: {err_str}")
                    return {"error": err_str}, 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"server_error: {str(e)}"}, 500

    try:
        paste_w = passport_width + 2 * border
        paste_h = passport_height + 2 * border

        # Calculate how many photos fit in one row + center offset
        cols_per_row = max(1, (a4_w + horizontal_gap) // (paste_w + horizontal_gap))
        total_row_width = cols_per_row * paste_w + (cols_per_row - 1) * horizontal_gap
        center_offset_x = (a4_w - total_row_width) // 2  # Equal left/right margins

        # Build all pages
        pages = []
        current_page = Image.new("RGB", (a4_w, a4_h), "white")
        x, y = center_offset_x, margin_y

        def new_page():
            nonlocal current_page, x, y
            pages.append(current_page)
            current_page = Image.new("RGB", (a4_w, a4_h), "white")
            x, y = center_offset_x, margin_y

        for passport_img, copies in passport_images:
            for _ in range(copies):
                # Move to next row if needed
                if x + paste_w > a4_w - center_offset_x:
                    x = center_offset_x
                    y += paste_h + spacing

                # Move to next page if needed
                if y + paste_h > a4_h - margin_y:
                    new_page()

                current_page.paste(passport_img, (x, y))
                print(f"DEBUG: Placed at x={x}, y={y}")
                x += paste_w + horizontal_gap

        pages.append(current_page)
        print(f"DEBUG: Total pages = {len(pages)}")

        # Export multi-page PDF
        output = BytesIO()
        dpi_val = 300 * scale
        if len(pages) == 1:
            pages[0].save(output, format="PDF", dpi=(dpi_val, dpi_val))
        else:
            pages[0].save(
                output,
                format="PDF",
                dpi=(dpi_val, dpi_val),
                save_all=True,
                append_images=pages[1:],
            )
        output.seek(0)
        print("DEBUG: Returning PDF to client")

        return send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="passport-sheet.pdf",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"pdf_generation_failed: {str(e)}"}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)