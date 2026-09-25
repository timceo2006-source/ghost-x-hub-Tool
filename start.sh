#!/bin/bash
CONFIG_DIR="/storage/emulated/0/GhostXHub"
SWITCH_DIR="$CONFIG_DIR/AutoSwitch"
SETTING_FILE="$CONFIG_DIR/Setting.txt"
COOKIE_FILE="$CONFIG_DIR/cookie.txt"
LICENSE_FILE="$CONFIG_DIR/license.key"

GREEN="\e[32m"
RED="\e[31m"
CYAN="\e[36m"
WHITE="\e[97m"
YELLOW="\e[93m"
RESET="\e[0m"

mkdir -p "$CONFIG_DIR" 2>/dev/null
mkdir -p "$SWITCH_DIR" 2>/dev/null

# ==========================================
# ระบบถามคีย์ก่อนเข้าเมนู
# ==========================================
if [ ! -f "$LICENSE_FILE" ]; then
    stty sane 2>/dev/null
    clear
    echo -e "${CYAN}========================================${RESET}"
    echo -e "${WHITE}           GHOST X HUB - AUTH           ${RESET}"
    echo -e "${CYAN}========================================${RESET}"
    read -p " [?] Enter License Key: " INPUT_KEY
    
    if [ -z "$INPUT_KEY" ]; then
        echo -e "\n${RED} [!] Key cannot be empty! Exiting...${RESET}"
        exit 1
    fi
    
    echo "$INPUT_KEY" > "$LICENSE_FILE"
    echo -e "${GREEN} [+] Key saved. Loading system...${RESET}"
    sleep 1
fi

clear
echo "Loading system... Please wait."

pkg update -y > /dev/null 2>&1
pkg install python openssh psmisc lsof ncurses-utils curl sqlite nano -y > /dev/null 2>&1

# [UPDATED] ติดตั้งไลบรารีที่จำเป็นสำหรับระบบความปลอดภัย
pip install flask requests cryptography > /dev/null 2>&1

if [ ! -f "$SETTING_FILE" ]; then
    echo "MODE=NORMAL" > "$SETTING_FILE"
    echo "MAP_ID=" >> "$SETTING_FILE"
    echo "CHECK_INTERVAL=30" >> "$SETTING_FILE"
    echo "TIMEOUT=40" >> "$SETTING_FILE"
    echo "LAUNCH_DELAY=15" >> "$SETTING_FILE"
    echo "LOOP_DELAY=60" >> "$SETTING_FILE"
fi

kill -9 $(lsof -t -i:5000) 2>/dev/null
su -c 'kill -9 $(lsof -t -i:5000)' 2>/dev/null
fuser -k -9 5000/tcp 2>/dev/null
pkill -9 -f python
killall -9 ssh 2>/dev/null
rm -f "$CONFIG_DIR/tunnel.log"

# ==========================================
# ดาวน์โหลดสคริปต์ทั้งหมด รวมถึงระบบความปลอดภัย
# ==========================================
rm -f main.py config.py injector.py auth.py pwf_license.py
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/main.py" -o main.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/config.py" -o config.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/injector.py" -o injector.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/auth.py" -o auth.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/pwf_license.py" -o pwf_license.py > /dev/null 2>&1

ssh -o StrictHostKeyChecking=no -R 80:localhost:5000 serveo.net > "$CONFIG_DIR/tunnel.log" 2>&1 &

for i in {1..10}; do
    url=$(grep -Eo 'https://[^ ]+\.serveousercontent\.com' "$CONFIG_DIR/tunnel.log" | head -n 1)
    if [ -n "$url" ]; then
        su -c "echo '$url' > /storage/emulated/0/Delta/Workspace/server_url.txt"
        break
    fi
    sleep 1
done

scan_apps() {
    > "$CONFIG_DIR/apps.txt"
    su -c 'pm list packages' | grep -i roblox | cut -d':' -f2 | tr -d '\r' | tr -d ' ' > "$CONFIG_DIR/apps.txt"
    app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
    if [ "$app_count" -eq 0 ]; then
        echo "com.roblox.client" > "$CONFIG_DIR/apps.txt"
    fi
}

if [ ! -f "$CONFIG_DIR/apps.txt" ]; then
    scan_apps
fi

# ==========================================
# ระบบดึงข้อมูลวันหมดอายุคีย์ล่วงหน้า
# ==========================================
echo "Fetching License Info..."
python -c "
import sys, os
try:
    from pwf_license import PWFLicense
    client = PWFLicense()
    with open('$LICENSE_FILE', 'r') as f:
        key = f.read().strip()
    res = client.login(key)
    if res.get('success'):
        print(res.get('expires', res.get('expiry', 'Valid (Active)')))
    else:
        print('Invalid or Expired')
except Exception:
    print('Unknown (Check pwf_license.py)')
" > "$CONFIG_DIR/key_expiry.txt" 2>/dev/null

stty sane 2>/dev/null

# ==========================================
# หน้าต่างเมนูหลัก
# ==========================================
while true; do
    clear
    MODE_STATUS=$(grep "^MODE=" "$SETTING_FILE" | cut -d'=' -f2)
    MAP_ID=$(grep "^MAP_ID=" "$SETTING_FILE" | cut -d'=' -f2)
    
    KEY_EXPIRY=$(cat "$CONFIG_DIR/key_expiry.txt" 2>/dev/null | tr -d '\r\n')
    if [ -z "$KEY_EXPIRY" ]; then
        KEY_EXPIRY="Unknown Error"
    fi
    
    echo -e "${CYAN}========================================${RESET}"
    echo -e "${WHITE}          Ghost X Tool Manager          ${RESET}"
    echo -e "${CYAN}========================================${RESET}"
    echo -e " [System Mode] : ${WHITE}${MODE_STATUS}${RESET}"
    echo -e " [Target Map]  : ${WHITE}${MAP_ID:-None}${RESET}"
    echo -e " [License Key] : ${GREEN}ACTIVE${RESET}"
    echo -e " [Key Expiry]  : ${YELLOW}${KEY_EXPIRY}${RESET}"
    echo -e "${CYAN}========================================${RESET}"
    echo -e " [1] Start System"
    echo -e " [2] Rescan Roblox Apps"
    echo -e " [3] Set Target Map (Place ID)"
    echo -e " [4] Auto Cookie Normal"
    echo -e " [5] Edit Cookie Normal"
    echo -e " [6] Toggle Mode (Normal / Auto-Switch)"
    echo -e " [7] Kill All Roblox Apps"
    echo -e " [8] Exit"
    echo -e "${CYAN}========================================${RESET}"
    read -p " Select Option: " opt

    case $opt in
        1)
            app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
            if [ "$MODE_STATUS" == "AUTO_SWITCH" ]; then
                if [ ! -f "$SWITCH_DIR/clone_1.txt" ]; then
                    echo -e "\n${RED}[!] Missing AutoSwitch files.${RESET}"
                    sleep 2
                    continue
                fi
            fi
            
            clear
            echo -e "${WHITE}[>] Initializing Engine...${RESET}"
            python -u main.py &
            PY_PID=$!
            
            echo -e "${CYAN}========================================${RESET}"
            echo -e "${GREEN}[+] SYSTEM IS RUNNING [${MODE_STATUS}]${RESET}"
            echo -e "${WHITE}[>] Press [ENTER] to stop the process.${RESET}"
            echo -e "${CYAN}========================================${RESET}\n"
            
            read -r
            
            echo -e "${RED}[!] Stopping System...${RESET}"
            kill -9 $PY_PID 2>/dev/null
            pkill -9 -f python 2>/dev/null
            sleep 1
            ;;
        2)
            echo -e "\n${WHITE}[>] Scanning for Roblox packages...${RESET}"
            scan_apps
            echo -e "${GREEN}[+] Scan complete.${RESET}"
            sleep 1
            ;;
        3)
            clear
            echo -e "${CYAN}========================================${RESET}"
            echo -e "${WHITE}           MAP CONFIGURATION            ${RESET}"
            echo -e "${CYAN}========================================${RESET}"
            echo -e " Current Map ID: ${WHITE}${MAP_ID:-None}${RESET}"
            echo -e "${CYAN}----------------------------------------${RESET}"
            read -p " Enter New Map ID (Leave blank to clear): " in_map
            sed -i "s/^MAP_ID=.*/MAP_ID=$in_map/" "$SETTING_FILE"
            echo -e "\n${GREEN}[+] Map ID updated successfully.${RESET}"
            sleep 1
            ;;
        4)
            clear
            app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
            echo -e "${CYAN}========================================${RESET}"
            echo -e "${WHITE}           AUTO COOKIE NORMAL           ${RESET}"
            echo -e "${CYAN}========================================${RESET}"
            > "$COOKIE_FILE" 
            for i in $(seq 1 $app_count); do
                pkg=$(sed -n "${i}p" "$CONFIG_DIR/apps.txt")
                echo -e "\n${WHITE}[Clone $i : $pkg]${RESET}"
                read -p " Paste Cookie: " cookie_data </dev/tty
                echo "$cookie_data" >> "$COOKIE_FILE"
            done
            echo -e "\n${GREEN}[+] Cookies saved successfully!${RESET}"
            sleep 2
            ;;
        5)
            if [ ! -f "$COOKIE_FILE" ]; then
                touch "$COOKIE_FILE"
            fi
            nano "$COOKIE_FILE"
            clear
            echo -e "\n${GREEN}[+] Returned to menu.${RESET}"
            sleep 1
            ;;
        6)
            if [ "$MODE_STATUS" == "NORMAL" ]; then
                sed -i "s/^MODE=.*/MODE=AUTO_SWITCH/" "$SETTING_FILE"
                app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
                for i in $(seq 1 $app_count); do touch "$SWITCH_DIR/clone_${i}.txt"; done
                echo -e "\n${GREEN}[+] Mode changed to AUTO_SWITCH${RESET}"
            else
                sed -i "s/^MODE=.*/MODE=NORMAL/" "$SETTING_FILE"
                echo -e "\n${GREEN}[+] Mode changed to NORMAL${RESET}"
            fi
            sleep 1
            ;;
        7)
            echo -e "\n${WHITE}[>] Terminating all Roblox instances...${RESET}"
            if [ -f "$CONFIG_DIR/apps.txt" ]; then
                while IFS= read -r pkg; do
                    if [ -n "$pkg" ]; then
                        clean_pkg=$(echo "$pkg" | tr -d '\r' | tr -d ' ')
                        echo -e "  |- Force stopping: $clean_pkg"
                        su -c "am force-stop $clean_pkg" > /dev/null 2>&1
                        su -c "killall -9 $clean_pkg" > /dev/null 2>&1 
                    fi
                done < "$CONFIG_DIR/apps.txt"
            fi
            echo -e "${GREEN}[+] All apps terminated.${RESET}"
            sleep 2
            ;;
        8|0)
            clear
            exit 0
            ;;
        *)
            echo -e "\n${RED}[!] Invalid Option!${RESET}"
            sleep 1
            ;;
    esac
done
