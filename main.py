from flask import Flask, request
import time
import threading
import os
import sys
import logging
from config import load_apps, get_settings, CONFIG_DIR
from injector import inject_cookie
from auth import get_switch_data

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
clients_expected_names = {} # [NEW] หน่วยความจำสำหรับล็อคเป้าชื่อตัวละคร

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
# สมอง AI ฉบับล็อคเป้าหมาย (ไร้การเดาสุ่ม)
# ==========================================
def resolve_clone_id(provided_id, username, cfg):
    if provided_id != "auto":
        return provided_id
    if not username or username == "Unknown":
        return None
        
    uname_lower = username.lower()

    # 1. แมตช์จากข้อมูลไฟล์คุกกี้ที่เรายัดเข้าไป (แม่นยำ 100% ไร้การเดา)
    for cid, exp_name in clients_expected_names.items():
        if exp_name == uname_lower:
            return cid

    # 2. แมตช์จากชื่อที่เคยเชื่อมต่อไว้แล้ว (สำหรับโหมด Normal ที่เล่นไอดีเดิม)
    for cid, uname in clients_usernames.items():
        if uname.lower() == uname_lower and uname != cid:
            return cid
            
    # 3. กรณีโหมด Normal จอใหม่เอี่ยม (อาศัยการเข้าคิวทีละจอตาม Launch Delay)
    curr = time.time()
    for cid in APPS_PACKAGE_NAMES.keys():
        seen = clients_last_seen.get(cid, 0)
        if seen == 0 or (curr - seen) > cfg["TIMEOUT"]:
            return cid
            
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
    raw_cid = data.get("clone_id")
    username = data.get("username")
    cfg = get_settings()
    
    clone_id = resolve_clone_id(raw_cid, username, cfg)
    if clone_id and cfg["MODE"] == "AUTO_SWITCH":
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
                print(f"{YELLOW} [!] Recovering {clone_id} (Attempt {retry_count + 1}/{MAX_RETRIES}){RESET}")
                print(f"{WHITE}  |- Terminating old process...{RESET}")
                os.system(f"su -c 'am force-stop {package_name}' > /dev/null 2>&1")
                time.sleep(1)
                
                if cfg["MODE"] == "AUTO_SWITCH":
                    print(f"{WHITE}  |- Injecting payload...{RESET}")
                    acc_name, acc_cookie = get_switch_data(clone_id, clients_combo_index)
                    if acc_cookie:
                        # [NEW] ล็อคเป้าชื่อตัวละครทันทีที่รู้ว่าจะยัดไอดีไหน!
                        clients_expected_names[clone_id] = acc_name.lower()
                        inject_cookie(package_name, clone_id, acc_cookie)
                
                print(f"{WHITE}  |- Booting application...{RESET}")
                if cfg["MAP_ID"]:
                    os.system(f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={cfg['MAP_ID']}\" -p {package_name}' > /dev/null 2>&1")
                else:
                    os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1' > /dev/null 2>&1")
                    
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
    
