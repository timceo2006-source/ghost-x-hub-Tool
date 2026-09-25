import os

CONFIG_DIR = "/storage/emulated/0/GhostXHub"
SETTING_FILE = f"{CONFIG_DIR}/Setting.txt"

def load_apps():
    apps = {}
    app_file = os.path.join(CONFIG_DIR, "apps.txt")
    if os.path.exists(app_file):
        with open(app_file, "r") as f:
            lines = f.read().splitlines()
            for i, pkg in enumerate(lines):
                if pkg.strip():
                    apps[f"clone_{i+1}"] = pkg.strip()
    if not apps:
        apps["clone_1"] = "com.roblox.client"
    return apps

def get_settings():
    settings = {"MODE": "NORMAL", "MAP_ID": "", "CHECK_INTERVAL": 30, "TIMEOUT": 40, "LAUNCH_DELAY": 15, "LOOP_DELAY": 60}
    if os.path.exists(SETTING_FILE):
        with open(SETTING_FILE, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k in settings:
                        try:
                            settings[k] = int(v) if v.isdigit() else v
                        except: pass
    return settings
  
