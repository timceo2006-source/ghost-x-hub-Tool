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

SQLITE_BIN = "/data/data/com.termux/files/usr/bin/sqlite3"

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

def extract_clean_cookie(raw_text):
    raw_text = raw_text.strip()
    if "_|WARNING" in raw_text:
        return "_|WARNING" + raw_text.split("_|WARNING", 1)[1]
    if ":" in raw_text:
        return raw_text.split(":")[-1].strip()
    return raw_text

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
                lines = [l for l in f.read().splitlines() if l.strip()]
                if len(lines) >= c_index:
                    raw_data = lines[c_index-1]
                    return "Normal_Mode", extract_clean_cookie(raw_data)
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
                
                parts = line_data.split(':', 1)
                name = parts[0] if len(parts) > 1 else "Unknown"
                return name, extract_clean_cookie(line_data)
        return None, None

# 🌟 ฟังก์ชันฉีดคุกกี้อัปเกรดเป็น DUAL-CORE INJECT (ตามวิชา V.16)
def inject_cookie(package_name, clone_id, acc_cookie, acc_name):
    data_dir = f"/data/data/{package_name}"
    webview_dir = f"{data_dir}/app_webview/Default"
    cookies_db = f"{webview_dir}/Cookies"
    xml_dir = f"{data_dir}/shared_prefs"
    xml_file = f"{xml_dir}/{package_name}_preferences.xml"
    
    print(f"{YELLOW}  ↳ [DEBUG] เริ่มกระบวนการ DUAL-CORE INJECT...{RESET}", flush=True)
    
    # 1. ล้างสมองเก่า (Native & Cache)
    os.system(f"su -c 'rm -rf {data_dir}/shared_prefs/*'")
    os.system(f"su -c 'rm -rf {data_dir}/files/appData/*'")
    os.system(f"su -c 'rm -rf {data_dir}/cache/*'")
    os.system(f"su -c 'rm -rf {webview_dir}/Cache/*'")
    
    # 2. แทรกซึม XML (สมองซีกซ้าย)
    xml_content = f"<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n    <string name=\".ROBLOSECURITY\">{acc_cookie}</string>\n</map>"
    tmp_xml = f"{CONFIG_DIR}/tmp_xml_{clone_id}.xml"
    with open(tmp_xml, "w") as f:
        f.write(xml_content)
    
    os.system(f"su -c 'mkdir -p {xml_dir}'")
    os.system(f"su -c 'cp {tmp_xml} {xml_file}'")
    os.system(f"rm -f {tmp_xml}")
    
    # 3. เตรียมฐานข้อมูล SQLite
    check_db = os.popen(f"su -c 'ls {cookies_db} 2>/dev/null'").read().strip()
    if not check_db:
        print(f"{YELLOW}  ↳ [DEBUG] ไม่พบโครงสร้าง Database! สร้างโครงสร้างใหม่ (รอ 7 วิ)...{RESET}", flush=True)
        os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1'")
        time.sleep(7)
        os.system(f"su -c 'am force-stop {package_name}'")
        time.sleep(2)
        
    os.system(f"su -c 'rm -f {cookies_db}-journal {cookies_db}-wal {cookies_db}-shm'")
    
    safe_cookie = acc_cookie.replace("'", "''")
    now = (int(time.time()) + 11644473600) * 1000000
    expires = now + (365 * 24 * 60 * 60 * 1000000)
    
    sql = (
        f"DELETE FROM cookies WHERE name='.ROBLOSECURITY';"
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
    
    # 4. แทรกซึม SQLite (สมองซีกขวา)
    sqlite_output = os.popen(f"su -c '{SQLITE_BIN} {cookies_db} < /data/local/tmp/inject_{clone_id}.sql' 2>&1").read().strip()
    
    if "not found" in sqlite_output or "inaccessible" in sqlite_output or "Error" in sqlite_output:
        print(f"{RED}  ↳ [ERROR] ❌ SQLite ล้มเหลว: {sqlite_output}{RESET}", flush=True)
    else:
        print(f"{CYAN}  ↳ [SUCCESS] ✅ ฉีดคุกกี้ XML + SQLite สำเร็จ: {acc_name}{RESET}", flush=True)
    
    # 5. ซ่อมแซมกรรมสิทธิ์ไฟล์ทั้งระบบ (ป้องกันเด้ง)
    app_uid = os.popen(f"su -c 'stat -c %u {data_dir}'").read().strip()
    if app_uid:
        os.system(f"su -c 'chown -R {app_uid}:{app_uid} {data_dir}'")
        os.system(f"su -c 'chmod -R 777 {xml_dir}'")
    
    os.system(f"su -c 'rm -f /data/local/tmp/inject_{clone_id}.sql'")
    os.system(f"rm -f {tmp_sql}")

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
        expected_name, _ = get_cookie_and_name(clone_id)
        
        if username and expected_name and expected_name != "Normal_Mode" and expected_name != "Unknown":
            if username.lower() != expected_name.lower():
                print(f"\n{RED}⚠️ [MISMATCH DETECTED] {clone_id} ไอดีผิดตัว!{RESET}")
                print(f"{RED}ต้องการ: {expected_name} | ในเกมคือ: {username}{RESET}")
                print(f"{YELLOW}กำลังบังคับปิดเกมเพื่อล้างไอดี...{RESET}\n", flush=True)
                
                clients_last_seen[clone_id] = 0
                return "MISMATCH", 200
        
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
        print(f"{CYAN}🎉 [{display_name}] ฟาร์มเสร็จสิ้น! กำลังเปลี่ยนไอดี...{RESET}")
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
                    print(f"{RED}✗ [{d_name}] OFFLINE (กำลังเชื่อมต่อใหม่...){RESET}")
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
                        print(f"{YELLOW}▶ [{display_name}] กำลังเปิดเกม...{RESET}", flush=True)
                    else:
                        print(f"{YELLOW}▶ [{display_name}] หลุดการเชื่อมต่อ. ลองใหม่ครั้งที่: {retry_count}/{MAX_RETRIES}{RESET}", flush=True)
                    
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
                            print(f"{YELLOW}  ↳ Cooldown: รอ {cfg['LAUNCH_DELAY']} วินาที...{RESET}", flush=True)
                            time.sleep(cfg["LAUNCH_DELAY"])
                            
                    clients_last_seen[clone_id] = time.time() + 45 
                    clients_retry_count[clone_id] = retry_count + 1
                else:
                    print(f"{RED}[{display_name}] ระงับการทำงาน 5 นาที (พยายามเข้าเกมหลายครั้งเกินไป){RESET}", flush=True)
                    clients_last_seen[clone_id] = current_time + 300 
        time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=auto_rejoin_checker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
                
