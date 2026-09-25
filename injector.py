import os
import time

SQLITE_BIN = "/data/data/com.termux/files/usr/bin/sqlite3"
CONFIG_DIR = "/storage/emulated/0/GhostXHub"

def inject_cookie(package_name, clone_id, acc_cookie):
    data_dir = f"/data/data/{package_name}"
    webview_dir = f"{data_dir}/app_webview/Default"
    cookies_db = f"{webview_dir}/Cookies"
    xml_dir = f"{data_dir}/shared_prefs"
    xml_file = f"{xml_dir}/{package_name}_preferences.xml"
    
    os.system(f"su -c 'rm -f {xml_dir}/prefs.xml' > /dev/null 2>&1")
    os.system(f"su -c 'rm -rf {data_dir}/files/appData/LocalStorage/*' > /dev/null 2>&1")
    os.system(f"su -c 'rm -f {xml_dir}/*.xml' > /dev/null 2>&1")
    os.system(f"su -c 'rm -rf {webview_dir}/Local\\ Storage/*' > /dev/null 2>&1")
    os.system(f"su -c 'rm -rf {webview_dir}/Session\\ Storage/*' > /dev/null 2>&1")
    os.system(f"su -c 'rm -rf {webview_dir}/Cache/*' > /dev/null 2>&1")
    
    xml_content = f"<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n    <string name=\".ROBLOSECURITY\">{acc_cookie}</string>\n</map>"
    tmp_xml = f"{CONFIG_DIR}/tmp_xml_{clone_id}.xml"
    with open(tmp_xml, "w") as f: f.write(xml_content)
    
    os.system(f"su -c 'mkdir -p {xml_dir} && cp {tmp_xml} {xml_file} && rm -f {tmp_xml}' > /dev/null 2>&1")
    
    check_db = os.popen(f"su -c 'ls {cookies_db} 2>/dev/null'").read().strip()
    if not check_db:
        os.system(f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1' > /dev/null 2>&1")
        time.sleep(7)
        os.system(f"su -c 'am force-stop {package_name}' > /dev/null 2>&1")
        
    os.system(f"su -c 'rm -f {cookies_db}-journal {cookies_db}-wal {cookies_db}-shm' > /dev/null 2>&1")
    
    safe_cookie = acc_cookie.replace("'", "''")
    now = (int(time.time()) + 11644473600) * 1000000
    expires = now + (365 * 24 * 60 * 60 * 1000000)
    sql = f"DELETE FROM cookies; INSERT INTO cookies (creation_utc, top_frame_site_key, host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires, is_persistent, priority, samesite, source_scheme, source_port, is_same_party) VALUES ({now}, '', '.roblox.com', '.ROBLOSECURITY', '{safe_cookie}', '', '/', {expires}, 1, 1, {now}, 1, 1, 1, -1, 1, 443, 0);"
    
    tmp_sql = f"{CONFIG_DIR}/inject_{clone_id}.sql"
    with open(tmp_sql, "w") as f: f.write(sql)
    
    os.system(f"su -c 'cp {tmp_sql} /data/local/tmp/inject_{clone_id}.sql && chmod 644 /data/local/tmp/inject_{clone_id}.sql' > /dev/null 2>&1")
    os.system(f"su -c '{SQLITE_BIN} {cookies_db} < /data/local/tmp/inject_{clone_id}.sql' > /dev/null 2>&1")
    
    app_uid = os.popen(f"su -c 'stat -c %u {data_dir}' 2>/dev/null").read().strip()
    if app_uid:
        os.system(f"su -c 'chown -R {app_uid}:{app_uid} {data_dir}' > /dev/null 2>&1")
        os.system(f"su -c 'chmod -R 777 {xml_dir}' > /dev/null 2>&1")
    
    os.system(f"su -c 'rm -f /data/local/tmp/inject_{clone_id}.sql && rm -f {tmp_sql}' > /dev/null 2>&1")
  
