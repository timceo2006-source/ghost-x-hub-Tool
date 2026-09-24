#!/bin/bash
CONFIG_DIR="/storage/emulated/0/GhostXHub"
SWITCH_DIR="$CONFIG_DIR/AutoSwitch"

echo "Installing required packages..."
pkg update -y > /dev/null 2>&1
pkg install python openssh psmisc lsof ncurses-utils curl sqlite -y > /dev/null 2>&1
pip install flask > /dev/null 2>&1

su -c "mkdir -p $CONFIG_DIR" 2>/dev/null
mkdir -p "$CONFIG_DIR" 2>/dev/null
mkdir -p "$SWITCH_DIR" 2>/dev/null

if [ ! -f "$CONFIG_DIR/settings.txt" ]; then
    echo "CHECK_INTERVAL=30" > "$CONFIG_DIR/settings.txt"
    echo "TIMEOUT=40" >> "$CONFIG_DIR/settings.txt"
    echo "LAUNCH_DELAY=20" >> "$CONFIG_DIR/settings.txt"
fi

GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
CYAN="\e[36m"
RESET="\e[0m"

stty sane 2>/dev/null
tput reset 2>/dev/null
clear

echo -e "${YELLOW}Initializing Ghost X Hub...${RESET}"
kill -9 $(lsof -t -i:5000) 2>/dev/null
su -c 'kill -9 $(lsof -t -i:5000)' 2>/dev/null
fuser -k -9 5000/tcp 2>/dev/null
killall -9 python 2>/dev/null
pkill -9 -f python
killall -9 ssh 2>/dev/null
rm -f "$CONFIG_DIR/tunnel.log"

# ==========================================
# บังคับโหลด server.py ใหม่ทุกครั้งที่เปิดสคริปต์
# ==========================================
echo -e "${YELLOW}Downloading Latest Core System...${RESET}"
rm -f server.py
curl -sL "https://raw.githubusercontent.com/timceo2006-source/ghost-x-hub-Tool/refs/heads/main/server.py" -o server.py
echo -e "${GREEN}System Ready!${RESET}"

echo -e "${CYAN}Establishing Secure Tunnel...${RESET}"
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
    stty sane 2>/dev/null
    clear
    echo -e "${CYAN}====================================${RESET}"
    echo -e "${YELLOW}  Scanning for Roblox Apps...${RESET}"
    echo -e "${CYAN}====================================${RESET}"
    
    > "$CONFIG_DIR/apps.txt"
    su -c 'pm list packages' | grep -i roblox | cut -d':' -f2 | tr -d '\r' | tr -d ' ' > "$CONFIG_DIR/apps.txt"
    
    app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
    if [ "$app_count" -gt 0 ]; then
        echo -e "${GREEN}  Found $app_count App(s):${RESET}"
        local i=1
        while IFS= read -r pkg; do
            if [ -n "$pkg" ]; then
                echo -e "  [$i] ${GREEN}$pkg${RESET}"
                i=$((i+1))
            fi
        done < "$CONFIG_DIR/apps.txt"
    else
        echo -e "${RED}  Warning: No apps found!${RESET}"
        echo "com.roblox.client" > "$CONFIG_DIR/apps.txt"
        echo -e "  [1] Default: com.roblox.client"
    fi
    
    echo -e "\n${YELLOW}  Returning to menu in 3 seconds...${RESET}"
    sleep 3
}

if [ ! -f "$CONFIG_DIR/apps.txt" ]; then
    scan_apps
fi

while true; do
    stty sane 2>/dev/null
    clear
    
    SWITCH_STATUS=$(cat "$CONFIG_DIR/switch_status.txt" 2>/dev/null || echo "OFF")
    if [ "$SWITCH_STATUS" == "ON" ]; then
        MODE_COLOR="${GREEN}ON${RESET}"
    else
        MODE_COLOR="${RED}OFF${RESET}"
    fi

    echo -e "${GREEN}====================================${RESET}"
    echo -e "${GREEN}          GHOST X HUB MENU          ${RESET}"
    echo -e "${GREEN}====================================${RESET}"
    echo -e "  [Current Mode: Auto-Switch is $MODE_COLOR]"
    echo -e "${GREEN}====================================${RESET}"
    echo -e "  [1] Start System"
    echo -e "  [2] Refresh/Scan Roblox Apps"
    echo -e "  [3] Setup Cookies & Map Config"
    echo -e "  [4] Tool Settings (Timeouts/Delays)"
    echo -e "  [6] Kill All Roblox Apps"
    echo -e "  [7] Toggle Auto-Switch Mode"
    echo -e "  [0] Exit"
    echo -e "${GREEN}====================================${RESET}"
    read -p "  Select Option: " opt

    case $opt in
        1)
            app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
            if [ "$SWITCH_STATUS" == "OFF" ]; then
                cookie_count=$(grep -c . "$CONFIG_DIR/cookie.txt" 2>/dev/null || echo 0)
                if [ "$cookie_count" -lt "$app_count" ] || [ "$cookie_count" -eq 0 ]; then
                    echo -e "\n${RED}  [Error] Normal mode: Missing cookies!${RESET}"
                    sleep 3
                    continue
                fi
            else
                if [ ! -f "$SWITCH_DIR/clone_1.txt" ]; then
                    echo -e "\n${RED}  [Error] Switch mode: No combo files found!${RESET}"
                    sleep 3
                    continue
                fi
            fi
            
            stty sane 2>/dev/null
            clear
            
            python -u server.py &
            PY_PID=$!
            
            echo -e "\n${CYAN}====================================${RESET}"
            echo -e "${GREEN}  > SYSTEM IS RUNNING (SQLite Mode) !${RESET}"
            echo -e "${YELLOW}  Mode: $( [ "$SWITCH_STATUS" == "ON" ] && echo "Auto-Switch" || echo "Normal" )${RESET}"
            echo -e "${YELLOW}  Press [ENTER] to STOP and return to Menu${RESET}"
            echo -e "${CYAN}====================================${RESET}\n"
            
            read -r
            
            echo -e "${RED}Stopping System...${RESET}"
            kill -9 $PY_PID 2>/dev/null
            pkill -9 -f server.py 2>/dev/null
            sleep 1
            ;;
        2)
            scan_apps
            ;;
        3)
            stty sane 2>/dev/null
            clear
            app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
            echo -e "${CYAN}====================================${RESET}"
            echo -e "${YELLOW}  Setup Normal Cookies for $app_count Clones${RESET}"
            echo -e "${CYAN}====================================${RESET}"
            
            > "$CONFIG_DIR/cookie.txt" 
            
            for i in $(seq 1 $app_count); do
                pkg=$(sed -n "${i}p" "$CONFIG_DIR/apps.txt")
                echo -e "\n${GREEN}Clone $i (${pkg})${RESET}"
                read -p "  Paste Cookie: " cookie_data </dev/tty
                echo "$cookie_data" >> "$CONFIG_DIR/cookie.txt"
            done
            
            echo -e "\n${CYAN}====================================${RESET}"
            read -p "  Enter Map ID (Leave blank to skip): " map_data </dev/tty
            if [ -n "$map_data" ]; then
                echo "$map_data" > "$CONFIG_DIR/map.txt"
            else
                > "$CONFIG_DIR/map.txt"
            fi
            
            echo -e "\n${GREEN}  Config saved successfully!${RESET}"
            sleep 2
            ;;
        4)
            stty sane 2>/dev/null
            clear
            echo -e "${CYAN}====================================${RESET}"
            echo -e "${YELLOW}  Global Settings Configuration${RESET}"
            echo -e "${CYAN}====================================${RESET}"
            
            read -p "  Status Check Interval (secs) [Default 30]: " val1 </dev/tty
            read -p "  Timeout Threshold (secs) [Default 40]: " val2 </dev/tty
            read -p "  Launch Cooldown (secs) [Default 20]: " val3 </dev/tty
            
            val1=${val1:-30}
            val2=${val2:-40}
            val3=${val3:-20}
            
            echo "CHECK_INTERVAL=$val1" > "$CONFIG_DIR/settings.txt"
            echo "TIMEOUT=$val2" >> "$CONFIG_DIR/settings.txt"
            echo "LAUNCH_DELAY=$val3" >> "$CONFIG_DIR/settings.txt"
            
            echo -e "\n${GREEN}  Settings saved successfully!${RESET}"
            sleep 2
            ;;
        6)
            echo -e "\n${RED}  Killing all Roblox apps...${RESET}"
            su -c 'pm list packages | grep roblox | cut -d":" -f2 | xargs -I {} am force-stop {}'
            echo -e "${GREEN}  All Roblox processes cleared!${RESET}"
            sleep 2
            ;;
        7)
            stty sane 2>/dev/null
            clear
            if [ "$SWITCH_STATUS" == "OFF" ]; then
                echo "ON" > "$CONFIG_DIR/switch_status.txt"
                app_count=$(grep -c . "$CONFIG_DIR/apps.txt")
                for i in $(seq 1 $app_count); do
                    touch "$SWITCH_DIR/clone_${i}.txt"
                done
                echo -e "${CYAN}====================================${RESET}"
                echo -e "${GREEN}  Auto-Switch Mode: ENABLED!${RESET}"
                echo -e "${YELLOW}  Files created in GhostXHub/AutoSwitch/${RESET}"
                echo -e "\n${YELLOW}  Format => Username:Password:Cookie${RESET}"
                echo -e "${CYAN}====================================${RESET}"
            else
                echo "OFF" > "$CONFIG_DIR/switch_status.txt"
                echo -e "${CYAN}====================================${RESET}"
                echo -e "${RED}  Auto-Switch Mode: DISABLED!${RESET}"
                echo -e "${CYAN}====================================${RESET}"
            fi
            read -p "  Press [ENTER] to return..." </dev/tty
            ;;
        0)
            stty sane 2>/dev/null
            clear
            exit 0
            ;;
        *)
            echo -e "\n${RED}  Invalid Option!${RESET}"
            sleep 1
            ;;
    esac
done
