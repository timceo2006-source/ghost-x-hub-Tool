#!/bin/bash
CONFIG_DIR="/storage/emulated/0/GhostXHub"
SWITCH_DIR="$CONFIG_DIR/AutoSwitch"
SETTING_FILE="$CONFIG_DIR/Setting.txt"

clear
echo "Loading system... Please wait."

pkg update -y > /dev/null 2>&1
pkg install python openssh psmisc lsof ncurses-utils curl sqlite -y > /dev/null 2>&1
pip install flask > /dev/null 2>&1

mkdir -p "$CONFIG_DIR" 2>/dev/null
mkdir -p "$SWITCH_DIR" 2>/dev/null

if [ ! -f "$SETTING_FILE" ]; then
    echo "MODE=NORMAL" > "$SETTING_FILE"
    echo "MAP_ID=" >> "$SETTING_FILE"
    echo "CHECK_INTERVAL=30" >> "$SETTING_FILE"
    echo "TIMEOUT=40" >> "$SETTING_FILE"
    echo "LAUNCH_DELAY=15" >> "$SETTING_FILE"
    echo "LOOP_DELAY=60" >> "$SETTING_FILE"
fi

GREEN="\e[32m"
RED="\e[31m"
CYAN="\e[36m"
WHITE="\e[97m"
RESET="\e[0m"

kill -9 $(lsof -t -i:5000) 2>/dev/null
su -c 'kill -9 $(lsof -t -i:5000)' 2>/dev/null
fuser -k -9 5000/tcp 2>/dev/null
pkill -9 -f python
killall -9 ssh 2>/dev/null
rm -f "$CONFIG_DIR/tunnel.log"

# ==========================================
# ลบไฟล์เก่า และดาวน์โหลดโมดูลใหม่แบบเงียบๆ
# ==========================================
rm -f main.py config.py injector.py auth.py server.py

curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/main.py" -o main.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/config.py" -o config.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/injector.py" -o injector.py > /dev/null 2>&1
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/auth.py" -o auth.py > /dev/null 2>&1

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

while true; do
    clear
    MODE_STATUS=$(grep "^MODE=" "$SETTING_FILE" | cut -d'=' -f2)
    MAP_ID=$(grep "^MAP_ID=" "$SETTING_FILE" | cut -d'=' -f2)
    
    echo -e "${CYAN}========================================${RESET}"
    echo -e "${WHITE}           GHOST X HUB PANEL            ${RESET}"
    echo -e "${CYAN}========================================${RESET}"
    echo -e " [System Mode] : ${WHITE}${MODE_STATUS}${RESET}"
    echo -e " [Target Map]  : ${WHITE}${MAP_ID:-None}${RESET}"
    echo -e "${CYAN}========================================${RESET}"
    echo -e " [1] Start System"
    echo -e " [2] Rescan Apps"
    echo -e " [3] Settings Configuration"
    echo -e " [4] Toggle Mode (Normal / Auto-Switch)"
    echo -e " [5] Kill All Apps"
    echo -e " [0] Exit"
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
            echo -e "${WHITE}             CONFIGURATION              ${RESET}"
            echo -e "${CYAN}========================================${RESET}"
            read -p " Map ID (Blank to skip): " in_map
            read -p " Launch Delay (Secs) [Default 15]: " in_ld
            read -p " Loop Delay (Secs) [Default 60]: " in_loop
            read -p " Timeout (Secs) [Default 40]: " in_time
            
            in_ld=${in_ld:-15}
            in_loop=${in_loop:-60}
            in_time=${in_time:-40}
            
            sed -i "s/^MAP_ID=.*/MAP_ID=$in_map/" "$SETTING_FILE"
            sed -i "s/^LAUNCH_DELAY=.*/LAUNCH_DELAY=$in_ld/" "$SETTING_FILE"
            sed -i "s/^LOOP_DELAY=.*/LOOP_DELAY=$in_loop/" "$SETTING_FILE"
            sed -i "s/^TIMEOUT=.*/TIMEOUT=$in_time/" "$SETTING_FILE"
            
            echo -e "\n${GREEN}[+] Settings Saved.${RESET}"
            sleep 1
            ;;
        4)
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
        5)
            echo -e "\n${WHITE}[>] Terminating processes...${RESET}"
            su -c 'pm list packages | grep roblox | cut -d":" -f2 | xargs -I {} am force-stop {}'
            echo -e "${GREEN}[+] All apps terminated.${RESET}"
            sleep 1
            ;;
        0)
            clear
            exit 0
            ;;
    esac
done
