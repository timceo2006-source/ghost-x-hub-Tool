from flask import Flask, request
import time
import threading
import os
import sys
import logging
import urllib.request
import json
from config import load_apps, get_settings, CONFIG_DIR
from injector import inject_cookie
from auth import get_switch_data

# ==========================================
# 1. ระบบรักษาความปลอดภัย (PWF AUTH)
# ==========================================
try:
    from pwf_license import PWFLicense
except ImportError:
    print("\033[91m [!] Missing Security Module (pwf_license.py). Please ensure the file is in the directory.\033[0m")
    sys.exit(1)

LICENSE_FILE = os.path.join(CONFIG_DIR, "license.key")

def verify_license():
    client = PWFLicense()
    
    while True:
        user_key = ""
        if os.path.exists(LICENSE_FILE):
            with open(LICENSE_FILE, "r") as f:
                user_key = f.read().strip()
                
        if not user_key:
            sys.stdout.write(f"\033[H\033[J")
            print(f"\033[96m========================================\033[0m")
            print(f"\033[97m           GHOST X HUB - AUTH           \033[0m")
            print(f"\033[96m========================================\033[0m")
            user_key = input(f"\033[93m [?] Enter License Key: \033[0m").strip()
            
            if not user_key:
                continue
                
        print(f"\033[97m [>] Verifying License...\033[0m")
        result = client.login(user_key)
        
        if result.get("success"):
            with open(LICENSE_FILE, "w") as f:
                f.write(user_key)
            print(f"\033[92m [+] License Verified! Welcome to Ghost X Hub.\033[0m")
            time.sleep(1)
            break
        else:
            print(f"\033[91m [-] Authentication Failed: {result.get('message', 'Invalid Key')}\033[0m")
            if os.path.exists(LICENSE_FILE):
                os.remove(LICENSE_FILE)
            time.sleep(2)
            
    def on_revoked(code, message):
        print(f"\n\033[91m========================================\033[0m")
        print(f"\033[91m [!] LICENSE REVOKED / EXPIRED \033[0m")
        print(f"\033[93m Reason: {message}\033[0m")
        print(f"\033[91m========================================\033[0m")
        print("\033[97m [>] Terminating Ghost X Hub Engine...\033[0m")
        os._exit(0)
        
    threading.Thread(target=client.run_heartbeat, args=(on_revoked,), daemon=True).start()
    return True

verify_license()

# ==========================================
# 2. ระบบหลักของ Ghost X Hub (Core Engine)
# ==========================================
os.environ.pop('WERKZEUG_RUN_MAIN', None)
os.environ.pop('WERKZEUG_SERVER_FD', None)

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app.logger.disabled = True

try:
    import flask.cli
    flask.cli.show_server_banner = lambda *args: None
except:
    pass

clients_last_seen = {}
clients_retry_count = {}
clients_usernames = {} 
clients_combo_index = {} 
clients_expected_names = {} 

APPS_PACKAGE_NAMES = load_apps()
MAX_RETRIES = 3

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
WHITE = '\033[97m'
YELLOW = '\033[93m'
RESET = '\033[0m'

for cid in APPS_PACKAGE_NAMES.keys():
    clients_last_seen[cid] = 0
    clients_retry_count[cid] = 0
    clients_usernames[cid] = cid 
    clients_combo_index[cid] = 0

# ==========================================
# [NEW] ระบบจัดเรียงจอ (Auto-Grid Layout)
# ==========================================
def arrange_window(package_name, clone_index):
    # ปรับแต่งขนาดจอตรงนี้ได้เลย (หน่วยเป็น Pixel)
    W = 360   # ความกว้างของ 1 จอ
    H = 480   # ความสูงของ 1 จอ
    COLS = 2  # จำนวนจอต่อ 1 แถว (จัดเรียงแบบ ซ้าย-ขวา)
    
    row = (clone_index - 1) // COLS
    col = (clone_index - 1) % COLS
    
    left = col * W
    top = row * H
    right = left + W
    bottom = top + H
    
    # คำสั่งดึง Task ID ของแอป และสั่งปรับขนาดผ่าน Window Manager
    cmd = f"su -c \"dumpsys activity tasks | grep '{package_name}' | grep -o 'taskId=[0-9]*' | cut -d'=' -f2 | head -n 1\""
    task_id = os.popen(cmd).read().strip()
    
    if task_id and task_id.isdigit():
        os.system(f"su -c 'am task resize {task_id} {left} {top} {right} {bottom}' > /dev/null 2>&1")

def fetch_roblox_name(cookie_str):
    try:
        cookie_str = cookie_str.strip()
        if not cookie_str: return None
        if "_|WARNING" in cookie_str:
            cookie_str = "_|WARNING" + cookie_str.split("_|WARNING", 1)[1]
            
        req = urllib.request.Request("https://users.roblox.com/v1/users/authenticated")
        req.add_header("Cookie", f".ROBLOSECURITY={cookie_str}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            return data.get("name")
    except:
        return None

def resolve_clone_id(provided_id, username, cfg):
    if provided_id != "auto":
        return provided_id
    if not username or username == "Unknown":
        return None
    uname_lower = username.lower()
    for cid, exp_name in clients_expected_names.items():
        if exp_name == uname_lower: return cid
    for cid, uname in clients_usernames.items():
        if uname.lower() == uname_lower and uname != cid: return cid
    curr = time.time()
    for cid in APPS_PACKAGE_NAMES.keys():
        seen = clients_last_seen.get(cid, 0)
        if seen == 0 or (curr - seen) > cfg["TIMEOUT"]: return cid
    return list(APPS_PACKAGE_NAMES.keys())[0]

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    raw_cid = data.get("clone_id")
    username = data.get("username") 
    cfg = get_settings()
    
    clone_id = resolve_clone_id(raw_cid, username, cfg)
    if not clone_id: return "WAIT", 200
    
    if cfg["MODE"] == "AUTO_SWITCH":
        expected_name, _ = get_switch_data(clone_id, clients_combo_index)
        if username and expected_name and expected_name != "Unknown":
            if username.lower() != expected_name.lower():
                clients_last_seen[clone_id] = 0
                return "MISMATCH", 200
    
    clients_last_seen[clone_id] = time.time()
    clients_retry_count[clone_id] = 0 
    if username and username != "Unknown": 
        clients_usernames[clone_id] = username
    return "OK", 200

@app.route('/task_complete', methods=['POST'])
def task_complete():
    data = request.json
    clone_id = resolve_clone_id(data.get("clone_id"), data.get("username"), get_settings())
    if clone_id and get_settings()["MODE"] == "AUTO_SWITCH":
        clients_combo_index[clone_id] = clients_combo_index.get(clone_id, 0) + 1
        clients_last_seen[clone_id] = 0 
    return "OK", 200

def print_ui(cfg, current_time):
    sys.stdout.write(f"\033[H\033[J")
    print(f"{CYAN}========================================{RESET}")
    print(f"{WHITE}             SYSTEM STATUS              {RESET}")
    print(f"{CYAN}========================================{RESET}")
    for cid in APPS_PACKAGE_NAMES.keys():
        l_seen = clients_last_seen.get(cid, 0)
        d_name = clients_usernames.get(cid, cid)
        if l_seen == 0 or (current_time - l_seen) > cfg["TIMEOUT"]:
            print(f"{RED} [-] {d_name} : OFFLINE{RESET}")
        else:
            print(f"{GREEN} [+] {d_name} : ONLINE{RESET}")
    print(f"{CYAN}========================================{RESET}\n")

def countdown(t, msg):
    for i in range(t, 0, -1):
        sys.stdout.write(f"\r{YELLOW} [>] {msg} : {i}s remaining...{RESET}   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r{' ' * 50}\r") 
    sys.stdout.flush()

def auto_rejoin_checker():
    time.sleep(1) 
    
    while True:
        current_time = time.time()
        cfg = get_settings()
        
        if cfg["MODE"] == "AUTO_SWITCH":
            for cid in APPS_PACKAGE_NAMES.keys():
                acc_name, _ = get_switch_data(cid, clients_combo_index)
                if acc_name and acc_name != "Unknown" and cid not in clients_expected_names:
                    clients_usernames[cid] = acc_name
                    clients_expected_names[cid] = acc_name.lower()
        else:
            cookie_file = os.path.join(CONFIG_DIR, "cookie.txt")
            if os.path.exists(cookie_file):
                with open(cookie_file, "r") as f:
                    cookies = f.read().splitlines()
                for i, cid in enumerate(APPS_PACKAGE_NAMES.keys()):
                    if i < len(cookies) and cookies[i].strip() and cid not in clients_expected_names:
                        sys.stdout.write(f"\r{WHITE} [>] Fetching API profile for {cid}...{' ' * 10}\r")
                        sys.stdout.flush()
                        uname = fetch_roblox_name(cookies[i])
                        if uname:
                            clients_usernames[cid] = uname
                            clients_expected_names[cid] = uname.lower()
        
        print_ui(cfg, current_time)
        
        sys.stdout.write(f"{WHITE} [>] Initiating system scan...{RESET}\n")
        time.sleep(0.5)
        
        offline_clones = []
        for clone_id in APPS_PACKAGE_NAMES.keys():
            sys.stdout.write(f"\r{WHITE} [>] Verifying {clone_id}...{' ' * 10}\r")
            sys.stdout.flush()
            time.sleep(0.3) 
            
            last_seen = clients_last_seen.get(clone_id, 0)
            d_name = clients_usernames.get(clone_id, clone_id)
            
            if last_seen == 0 or (current_time - last_seen) > cfg["TIMEOUT"]:
                sys.stdout.write(f"{RED} [-] {clone_id} ({d_name}) is OFFLINE{' ' * 10}{RESET}\n")
                offline_clones.append(clone_id)
            else:
                sys.stdout.write(f"{GREEN} [+] {clone_id} ({d_name}) is ONLINE{' ' * 10}{RESET}\n")
        
        print(f"{CYAN}----------------------------------------{RESET}")
        
        action_taken = False
        for clone_id in offline_clones:
            retry_count = clients_retry_count.get(clone_id, 0)
            package_name = APPS_PACKAGE_NAMES.get(clone_id)
            
            if retry_count < MAX_RETRIES:
                d_name = clients_usernames.get(clone_id, clone_id)
                print(f"{YELLOW} [!] Recovering {clone_id} ({d_name}) (Attempt {retry_count + 1}/{MAX_RETRIES}){RESET}")
                print(f"{WHITE}  |- Terminating old process...{RESET}")
                os.system(f"su -c 'am force-stop {package_name}' > /dev/null 2>&1")
                time.sleep(1)
                
                if cfg["MODE"] == "AUTO_SWITCH":
                    print(f"{WHITE}  |- Injecting payload...{RESET}")
                    acc_name, acc_cookie = get_switch_data(clone_id, clients_combo_index)
                    if acc_cookie:
                        inject_cookie(package_name, clone_id, acc_cookie)
                
                print(f"{WHITE}  |- Booting application...{RESET}")
                if cfg["MAP_ID"]:
                    os.system(f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={cfg['MAP_ID']}\" -p {package_name}' > /dev/null 2>&1")
                else:
                    os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1' > /dev/null 2>&1")
                    
                # [NEW] จัดหน้าต่างแอปให้เล็กลงและเข้าที่
                print(f"{WHITE}  |- Arranging window layout...{RESET}")
                time.sleep(4) # รอให้แอปเปิดติดสักพักถึงจะมี Task ID
                try:
                    c_idx = int(clone_id.split('_')[1])
                except:
                    c_idx = 1
                arrange_window(package_name, c_idx)
                    
                clients_last_seen[clone_id] = time.time() + 45 
                clients_retry_count[clone_id] = retry_count + 1
                action_taken = True
                
                if cfg["LAUNCH_DELAY"] > 0:
                    countdown(cfg["LAUNCH_DELAY"], f"Boot Delay ({clone_id})")
            else:
                print(f"{RED} [!] {clone_id} suspended for 5 mins (Max retries reached).{RESET}")
                clients_last_seen[clone_id] = time.time() + 300 

        if action_taken:
            print(f"{CYAN}----------------------------------------{RESET}")

        countdown(cfg["LOOP_DELAY"], "Next system scan in")

if __name__ == '__main__':
    threading.Thread(target=auto_rejoin_checker, daemon=True).start()
    try:
        cli = sys.modules.get('flask.cli')
        if cli:
            cli.show_server_banner = lambda *x: None
    except:
        pass
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
    
