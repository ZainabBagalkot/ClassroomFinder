import streamlit as st
import csv
import os
import re
from datetime import datetime

st.set_page_config(page_title="Classroom Finder", page_icon="🏫", layout="centered")
st.title("🏫 Empty Classroom Finder")

# Get the directory where app.py is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "2026-2027 Schedule - Fall 2026.csv")
MANUAL_LAB_FILE = os.path.join(SCRIPT_DIR, "manual_lab_rooms.txt")

DAY_START = 8 * 60
DAY_END = 21 * 60

# --- Helper Functions ---
def to_min(t):
    t = (t or "").strip().replace("\u202f", " ")
    if not t or t.upper() in {"N/A", "OL", "ONLINE", ""}: return None
    try:
        return datetime.strptime(t, "%I:%M %p").hour * 60 + datetime.strptime(t, "%I:%M %p").minute
    except ValueError:
        return None

def fmt(m):
    h, mi = divmod(m, 60)
    ampm = "am" if h < 12 else "pm"
    h = h % 12 or 12
    return f"{h}:{mi:02d}{ampm}"

def merge_and_get_gaps(intervals):
    merged = []
    for s, e in sorted(intervals):
        if not merged or s > merged[-1][1]: merged.append([s, e])
        else: merged[-1][1] = max(merged[-1][1], e)
    gaps = []
    cur = DAY_START
    for s, e in merged:
        if s > cur: gaps.append((cur, s))
        cur = max(cur, e)
    if cur < DAY_END: gaps.append((cur, DAY_END))
    return gaps

# --- Data Loading ---
# Notice: We REMOVED @st.cache_data so that if you edit the CSV or the text file, it updates immediately!
def load_data():
    room_day = {}
    lab_rooms = set()
    
    if os.path.exists(MANUAL_LAB_FILE):
        with open(MANUAL_LAB_FILE, 'r', encoding='utf-8') as f:
            lab_rooms.update(line.strip() for line in f if line.strip())

    if not os.path.exists(CSV_FILE):
        st.error(f"Error: Could not find the CSV file at {CSV_FILE}")
        return {}, set()

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = None
        for row in reader:
            if row and "Room #" in row:
                headers = row
                break
                
        if not headers: return {}, set()

        r_idx, d_idx, s_idx, e_idx = headers.index("Room #"), headers.index("Days"), headers.index("Time Start"), headers.index("Time End")
        c_idx, sec_idx = headers.index("Course Name"), headers.index("Sect#")

        for row in reader:
            if len(row) <= max(r_idx, d_idx, s_idx, e_idx): continue
            room = row[r_idx].strip()
            if not room or ' ' in room or room.upper().startswith("TBD"): continue
            
            start, end = to_min(row[s_idx]), to_min(row[e_idx])
            if start is None or end is None: continue

            # Auto-detect labs
            if 'L' in row[sec_idx].upper() or any(x in row[c_idx].upper() for x in ["LAB", "WORKSHOP", "STUDIO"]):
                lab_rooms.add(room)

            days = set()
            ds = row[d_idx].upper()
            if "M" in ds: days.add("Mon")
            if "T" in ds: days.add("Tue")
            if "W" in ds: days.add("Wed")
            if "R" in ds: days.add("Thu")
            if "F" in ds: days.add("Fri")
            
            for d in days:
                room_day.setdefault(room, {}).setdefault(d, []).append((start, end))
                
    return room_day, lab_rooms

room_day, lab_rooms = load_data()
all_rooms = sorted([r for r in room_day.keys() if r not in lab_rooms])

# --- Streamlit UI ---
if not room_day:
    st.stop()

mode = st.radio("What would you like to search?", ["Time & Day", "Block & Time & Day"])

selected_day = st.selectbox("Day", ["Mon", "Tue", "Wed", "Thu", "Fri"])

block = None
if mode == "Block & Time & Day":
    block = st.selectbox("Block", sorted(list(set([r[0] for r in all_rooms]))))

col1, col2 = st.columns(2)
with col1:
    start_time = st.text_input("Start Time (e.g., 3:50pm or 4pm)", "3:50pm")
with col2:
    end_time = st.text_input("End Time (e.g., 5:00pm)", "5:00pm")

def parse_t(t):
    t = t.lower().replace(" ", "")
    if re.match(r"^\d{1,2}(am|pm)$", t): t = t[:-2] + ":00" + t[-2:]
    try: return datetime.strptime(t, "%I:%M%p").hour * 60 + datetime.strptime(t, "%I:%M%p").minute
    except: return None

req_start, req_end = parse_t(start_time), parse_t(end_time)

if st.button("🔍 Find Free Rooms", use_container_width=True):
    if req_start is None or req_end is None or req_start >= req_end:
        st.error("Invalid times entered. Please use a format like '4pm' or '4:00pm'.")
    else:
        results = []
        for room in all_rooms:
            if mode == "Block & Time & Day" and not room.startswith(block): continue
            
            gaps = merge_and_get_gaps(room_day[room].get(selected_day, []))
            for gs, ge in gaps:
                if gs <= req_start and req_end <= ge:
                    results.append({"Room": room, "Free From": fmt(gs), "Free Until": fmt(ge)})
                    break

        if results:
            st.success(f"Found {len(results)} free rooms on {selected_day}!")
            st.dataframe(results, use_container_width=True, hide_index=True)
        else:
            st.warning("No classrooms are completely free during this time.")