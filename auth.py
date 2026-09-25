import os
from config import CONFIG_DIR

def extract_clean_cookie(raw_text):
    raw_text = raw_text.strip()
    if "_|WARNING" in raw_text: return "_|WARNING" + raw_text.split("_|WARNING", 1)[1]
    if ":" in raw_text: return raw_text.split(":")[-1].strip()
    return raw_text

def get_switch_data(clone_id, clients_combo_index):
    combo_file = os.path.join(CONFIG_DIR, "AutoSwitch", f"{clone_id}.txt")
    curr_line = clients_combo_index.get(clone_id, 0)
    if os.path.exists(combo_file):
        with open(combo_file, "r") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
            if len(lines) == 0: return None, None
            line_data = lines[curr_line % len(lines)]
            parts = line_data.split(':', 1)
            name = parts[0] if len(parts) > 1 else "Unknown"
            return name, extract_clean_cookie(line_data)
    return None, None
  
