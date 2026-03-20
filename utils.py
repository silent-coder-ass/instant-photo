import json
import os
import uuid
import bcrypt

if os.environ.get("VERCEL"):
    CONFIG_FILE = os.path.join("/tmp", "config.json")
    DEFAULT_CONFIG_FILE = os.path.join("data", "config.json")
else:
    CONFIG_FILE = os.path.join("data", "config.json")
    DEFAULT_CONFIG_FILE = None

def load_config():
    if not os.path.exists(CONFIG_FILE):
        if DEFAULT_CONFIG_FILE and os.path.exists(DEFAULT_CONFIG_FILE):
            with open(DEFAULT_CONFIG_FILE, "r") as f:
                data = json.load(f)
            save_config(data)
            return data
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config_data):
    # Ensure data directory exists
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=2)

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_active_api_key(service="remove_bg"):
    config = load_config()
    keys = config.get("api_keys", [])
    for key in keys:
        if key.get("service") == service and key.get("active"):
            return key
    return None

def rotate_api_key(failed_key_id, service="remove_bg"):
    """Marks failed_key_id as inactive, activates the next available key for the service."""
    config = load_config()
    keys = config.get("api_keys", [])
    
    # 1. Mark current as failed
    for k in keys:
        if k.get("id") == failed_key_id:
            k["active"] = False
            k["last_failed"] = True

    # 2. Find next available key
    for k in keys:
        if k.get("service") == service and not k.get("last_failed"):
            k["active"] = True
            save_config(config)
            return k
            
    # If all failed, reset last_failed and try again? Or just fail. Let's just fail.
    save_config(config)
    return None
