from flask import Flask, request
import time
import threading
import os

app = Flask(__name__)
clients_last_seen = {}
clients_retry_count = {}
clients_usernames = {} 
clients_combo_index = {} 

MAX_RETRIES = 3
CONFIG_DIR = "/storage/emulated/0/GhostXHub"
APPS_PACKAGE_NAMES = {}

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def load_apps():
    app_file = os.path.join(CONFIG_DIR, "apps.txt")
    APPS_PACKAGE_NAMES.clear()
    if os.path.exists(app_file):
        with open(app_file, "r") as f:
            lines = f.read().splitlines()
            for i, pkg in enumerate(lines):
                if pkg.strip():
                    APPS_PACKAGE_NAMES[f"clone_{i+1}"] = pkg.strip()
    
    if not APPS_PACKAGE_NAMES:
        APPS_PACKAGE_NAMES["clone_1"] = "com.roblox.client"

def get_settings():
    settings = {"CHECK_INTERVAL": 30, "TIMEOUT": 40, "LAUNCH_DELAY": 20}
    set_file = os.path.join(CONFIG_DIR, "settings.txt")
    if os.path.exists(set_file):
        with open(set_file, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k in settings:
                        try: settings[k] = int(v)
                        except: pass
    return settings

def get_map_id():
    map_file = os.path.join(CONFIG_DIR, "map.txt")
    if os.path.exists(map_file):
        with open(map_file, "r") as f:
            return f.read().strip()
    return ""

def get_cookie_and_name(clone_id):
    try:
        c_index = int(clone_id.split('_')[1])
    except:
        c_index = 1
        
    status_file = os.path.join(CONFIG_DIR, "switch_status.txt")
    switch_on = False
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            if "ON" in f.read():
                switch_on = True

    if not switch_on:
        cookie_file = os.path.join(CONFIG_DIR, "cookie.txt")
        if os.path.exists(cookie_file):
            with open(cookie_file, "r") as f:
                lines = f.read().splitlines()
                if len(lines) >= c_index:
                    return "Normal_Mode", lines[c_index-1]
        return None, None
    else:
        combo_file = os.path.join(CONFIG_DIR, "AutoSwitch", f"{clone_id}.txt")
        curr_line = clients_combo_index.get(clone_id, 0)
        if os.path.exists(combo_file):
            with open(combo_file, "r") as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
                if len(lines) == 0:
                    return None, None
                safe_line = curr_line % len(lines)
                line_data = lines[safe_line]
                
                parts = line_data.split(':', 2)
                if len(parts) == 3:
                    return parts[0], parts[2]
                else:
                    return "Unknown", line_data
        return None, None

def inject_cookie(package_name, clone_id, acc_cookie, acc_name):
    data_dir = f"/data/data/{package_name}"
    webview_dir = f"{data_dir}/app_webview/Default"
    cookies_db = f"{webview_dir}/Cookies"
    
    # 1. ถอนรากถอนโคนไอดีเก่า (ลบ XML เดิมทิ้ง เพื่อไม่ให้เกมแอบไปอ่าน)
    os.system(f"su -c 'rm -f {data_dir}/shared_prefs/com.roblox.client_preferences.xml'")
    os.system(f"su -c 'rm -rf {data_dir}/cache/*'")
    os.system(f"su -c 'mkdir -p {webview_dir}'")
    
    safe_cookie = acc_cookie.replace("'", "''")
    now = (int(time.time()) + 11644473600) * 1000000
    expires = now + (365 * 24 * 60 * 60 * 1000000)
    
    sql = (
        f"DELETE FROM cookies WHERE host_key='.roblox.com' AND name='.ROBLOSECURITY';"
        f"INSERT INTO cookies (creation_utc, top_frame_site_key, host_key, name, value, encrypted_value, "
        f"path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires, is_persistent, "
        f"priority, samesite, source_scheme, source_port, is_same_party) VALUES ("
        f"{now}, '', '.roblox.com', '.ROBLOSECURITY', '{safe_cookie}', '', '/', "
        f"{expires}, 1, 1, {now}, 1, 1, 1, -1, 1, 443, 0);"
    )
    
    tmp_sql = f"{CONFIG_DIR}/inject_{clone_id}.sql"
    with open(tmp_sql, "w") as f:
        f.write(sql)
    
    os.system(f"su -c 'cp {tmp_sql} /data/local/tmp/inject_{clone_id}.sql'")
    os.system(f"su -c 'chmod 644 /data/local/tmp/inject_{clone_id}.sql'")
    os.system(f"su -c 'rm -f {cookies_db}-journal {cookies_db}-wal {cookies_db}-shm'")
    os.system(f"su -c 'sqlite3 {cookies_db} < /data/local/tmp/inject_{clone_id}.sql'")
    
    uid_cmd = f"su -c 'stat -c %u {data_dir}'"
    app_uid = os.popen(uid_cmd).read().strip()
    if app_uid:
        os.system(f"su -c 'chown -R {app_uid}:{app_uid} {data_dir}/app_webview'")
        os.system(f"su -c 'chmod 660 {cookies_db}'")
    
    os.system(f"su -c 'rm -f /data/local/tmp/inject_{clone_id}.sql'")
    os.system(f"rm -f {tmp_sql}")
    print(f"{CYAN}  ↳ [SQLite Inject Success]: {acc_name}{RESET}", flush=True)

load_apps()
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
    
    if clone_id:
        # 2. ระบบสแกนตรวจสอบความถูกต้องของไอดี
        expected_name, _ = get_cookie_and_name(clone_id)
        
        if username and expected_name and expected_name not in ["Normal_Mode", "Unknown"]:
            # ถ้าชื่อในเกม ไม่ตรงกับ ชื่อในไฟล์คอมโบ (เทียบแบบไม่สนพิมพ์เล็กพิมพ์ใหญ่)
            if username.lower() != expected_name.lower():
                print(f"\n{RED}⚠️ [MISMATCH DETECTED] {clone_id} has wrong account!{RESET}")
                print(f"{RED}Expected: {expected_name} | In-Game: {username}{RESET}")
                print(f"{YELLOW}Force killing app to clear stuck ID...{RESET}\n", flush=True)
                
                # บังคับรีเซ็ตเวลาเป็น 0 เพื่อให้ลูป Auto-rejoin จับเตะทิ้งทันที
                clients_last_seen[clone_id] = 0
                return "MISMATCH", 200
        
        # ถ้าชื่อถูกต้อง หรือเป็นโหมดธรรมดา ให้อัปเดตสถานะออนไลน์
        clients_last_seen[clone_id] = time.time()
        clients_retry_count[clone_id] = 0 
        if username:
            clients_usernames[clone_id] = username
            
    return "OK", 200

@app.route('/task_complete', methods=['POST'])
def task_complete():
    data = request.json
    clone_id = data.get("clone_id")
    if clone_id:
        display_name = clients_usernames.get(clone_id, clone_id)
        print(f"\n{CYAN}=========================================={RESET}")
        print(f"{CYAN}🎉 [{display_name}] FINISHED TASK! Switching account...{RESET}")
        print(f"{CYAN}=========================================={RESET}\n", flush=True)
        clients_combo_index[clone_id] = clients_combo_index.get(clone_id, 0) + 1
        clients_last_seen[clone_id] = 0 
    return "OK", 200

def auto_rejoin_checker():
    time.sleep(3) 
    last_report_time = 0
    while True:
        current_time = time.time()
        cfg = get_settings()
        
        if current_time - last_report_time >= cfg["CHECK_INTERVAL"]:
            print(f"\n{CYAN}--- [ STATUS REPORT ] ---{RESET}")
            for cid in APPS_PACKAGE_NAMES.keys():
                l_seen = clients_last_seen.get(cid, 0)
                d_name = clients_usernames.get(cid, cid)
                if l_seen == 0 or (current_time - l_seen) > cfg["TIMEOUT"]:
                    print(f"{RED}✗ [{d_name}] OFFLINE (Rejoining soon...){RESET}")
                else:
                    print(f"{GREEN}✓ [{d_name}] ONLINE{RESET}")
            print(f"{CYAN}-------------------------{RESET}\n", flush=True)
            last_report_time = current_time

        for clone_id, last_seen in list(clients_last_seen.items()):
            if current_time - last_seen > cfg["TIMEOUT"]:
                retry_count = clients_retry_count.get(clone_id, 0)
                display_name = clients_usernames.get(clone_id, clone_id) 
                
                if retry_count < MAX_RETRIES:
                    if retry_count == 0:
                        print(f"{YELLOW}▶ [{display_name}] Starting App...{RESET}", flush=True)
                    else:
                        print(f"{YELLOW}▶ [{display_name}] Disconnected. Retry: {retry_count}/{MAX_RETRIES}{RESET}", flush=True)
                    
                    package_name = APPS_PACKAGE_NAMES.get(clone_id)
                    if package_name:
                        os.system(f"su -c 'am force-stop {package_name}'")
                        time.sleep(2)
                        
                        acc_name, acc_cookie = get_cookie_and_name(clone_id)
                        if acc_cookie:
                            inject_cookie(package_name, clone_id, acc_cookie, acc_name)
                        
                        map_id = get_map_id()
                        if map_id:
                            os.system(f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={map_id}\" -p {package_name}'")
                        else:
                            os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1'")
                        
                        if cfg["LAUNCH_DELAY"] > 0:
                            print(f"{YELLOW}  ↳ Cooldown: Waiting {cfg['LAUNCH_DELAY']}s...{RESET}", flush=True)
                            time.sleep(cfg["LAUNCH_DELAY"])
                            
                    clients_last_seen[clone_id] = time.time() + 45 
                    clients_retry_count[clone_id] = retry_count + 1
                else:
                    print(f"{RED}[{display_name}] Suspended for 5 mins.{RESET}", flush=True)
                    clients_last_seen[clone_id] = current_time + 300 
        time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=auto_rejoin_checker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
    
