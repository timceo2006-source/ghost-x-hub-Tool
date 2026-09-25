from flask import Flask, request
import time
import threading
import os
import sys
import logging
from config import load_apps, get_settings, CONFIG_DIR
from injector import inject_cookie
from auth import get_switch_data

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

clients_last_seen = {}
clients_retry_count = {}
clients_usernames = {} 
clients_combo_index = {} 
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

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    clone_id = data.get("clone_id")
    username = data.get("username") 
    cfg = get_settings()
    
    if clone_id:
        if cfg["MODE"] == "AUTO_SWITCH":
            expected_name, _ = get_switch_data(clone_id, clients_combo_index)
            if username and expected_name and expected_name != "Unknown":
                if username.lower() != expected_name.lower():
                    clients_last_seen[clone_id] = 0
                    return "MISMATCH", 200
        
        clients_last_seen[clone_id] = time.time()
        clients_retry_count[clone_id] = 0 
        if username: clients_usernames[clone_id] = username
    return "OK", 200

@app.route('/task_complete', methods=['POST'])
def task_complete():
    data = request.json
    clone_id = data.get("clone_id")
    cfg = get_settings()
    if clone_id and cfg["MODE"] == "AUTO_SWITCH":
        clients_combo_index[clone_id] = clients_combo_index.get(clone_id, 0) + 1
        clients_last_seen[clone_id] = 0 
    return "OK", 200

def print_ui(cfg):
    sys.stdout.write(f"\033[H\033[J")
    print(f"{CYAN}========================================{RESET}")
    print(f"{WHITE}             SYSTEM STATUS              {RESET}")
    print(f"{CYAN}========================================{RESET}")
    current_time = time.time()
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
        sys.stdout.write(f"\r{YELLOW} [>] {msg} : {i}s remaining...{RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r{' ' * 50}\r")
    sys.stdout.flush()

def auto_rejoin_checker():
    time.sleep(2) 
    last_report_time = 0
    
    while True:
        current_time = time.time()
        cfg = get_settings()
        
        if current_time - last_report_time >= cfg["CHECK_INTERVAL"]:
            print_ui(cfg)
            last_report_time = current_time

        action_taken = False
        for clone_id, last_seen in list(clients_last_seen.items()):
            if time.time() - last_seen > cfg["TIMEOUT"]:
                retry_count = clients_retry_count.get(clone_id, 0)
                package_name = APPS_PACKAGE_NAMES.get(clone_id)
                
                if retry_count < MAX_RETRIES:
                    sys.stdout.write(f"\r{WHITE} [>] Processing {clone_id}...{' ' * 20}\r")
                    sys.stdout.flush()
                    
                    os.system(f"su -c 'am force-stop {package_name}' > /dev/null 2>&1")
                    time.sleep(1)
                    
                    if cfg["MODE"] == "AUTO_SWITCH":
                        acc_name, acc_cookie = get_switch_data(clone_id, clients_combo_index)
                        if acc_cookie:
                            inject_cookie(package_name, clone_id, acc_cookie)
                    
                    if cfg["MAP_ID"]:
                        os.system(f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={cfg['MAP_ID']}\" -p {package_name}' > /dev/null 2>&1")
                    else:
                        os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1' > /dev/null 2>&1")
                        
                    clients_last_seen[clone_id] = time.time() + 45 
                    clients_retry_count[clone_id] = retry_count + 1
                    action_taken = True
                    
                    print_ui(cfg) 
                    
                    if cfg["LAUNCH_DELAY"] > 0:
                        countdown(cfg["LAUNCH_DELAY"], "Launch Delay")
                else:
                    clients_last_seen[clone_id] = time.time() + 300 
        
        if action_taken and cfg.get("LOOP_DELAY", 0) > 0:
            countdown(cfg["LOOP_DELAY"], "Loop Delay")
        else:
            time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=auto_rejoin_checker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
    
