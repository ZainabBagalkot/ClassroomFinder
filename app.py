import streamlit as st
import csv
import os
import re
from datetime import datetime

st.set_page_config(page_title="Classroom Finder", page_icon="🏫", layout="centered")
st.title("🏫 Empty Classroom Finder")

CSV_FILE = "2026-2027 Schedule - Fall 2026.csv"
MANUAL_LAB_FILE = "manual_lab_rooms.txt"

DAY_START = 8 * 60
DAY_END = 21 * 60

def clean_room_name(r):
    # Removes spaces and hyphens, makes uppercase. E-009 -> E009
    return re.sub(r'[\s\-]', '', str(r).upper())

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

def load_data():
    room_day = {}
    
    # --- MANUAL BLACKLIST ---
    # Any room added here will be permanently ignored.
    lab_rooms = set()
    lab_rooms.add(clean_room_name("E009")) 
    lab_rooms.add(clean_room_name("E-009"))
    
    # Also read from the text file if it exists
    if os.path.exists(MANUAL_LAB_FILE):
        with open(MANUAL_LAB_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                clean_name = line.strip()
                if clean_name:
                    lab_rooms.add(clean_room_name(clean_name))

    if not os.path.exists(CSV_FILE):
        st.error(f"Error: Could not find the CSV file at {CSV_FILE}")
        return {}, set(), set()

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = None
        for row in reader:
            if row and "Room #" in row:
                headers = row
                break
                
        if not headers: return {}, set(), set()

        r_idx, d_idx, s_idx, e_idx = headers.index("Room #"), headers.index("Days"), headers.index("Time Start"), headers.index("Time End")
        c_idx, sec_idx = headers.index("Course Name"), headers.index("Sect#")

        for row in reader:
            if len(row) <= max(r_idx, d_idx, s_idx, e_idx): continue
            
            room_raw = row[r_idx].strip()
            room_clean = clean_room_name(room_raw)
            
            if not room_raw or ' ' in room_raw or room_raw.upper().startswith("TBD"): continue
            
            start, end = to_min(row[s_idx]), to_min(row[e_idx])
            if start is None or end is None: continue

            # Auto-detect labs from CSV
            if 'L' in row[sec_idx].upper() or any(x in row[c_idx].upper() for x in ["LAB", "WORKSHOP", "STUDIO"]):
                lab_rooms.add(room_clean)

            days = set()
            ds = row[d_idx].upper()
            if "M" in ds: days.add("Mon")
            if "T" in ds: days.add("Tue")
            if "W" in ds: days.add("Wed")
            if "R" in ds: days.add("Thu")
            if "F" in ds: days.add("Fri")
            
            for d in days:
                room_day.setdefault(room_raw, {}).setdefault(d, []).append((start, end))
                
    return room_day, lab_rooms, lab_rooms

# Force Streamlit to re-read the file on every single run
room_day, _, lab_rooms = load_data()

# Build the final list of allowed rooms
all_rooms = []
for r in room_day.keys():
    if clean_room_name(r) not in lab_rooms:
        all_rooms.append(r)
all_rooms = sorted(all_rooms)

# --- Streamlit UI ---
if not room_day:
    st.stop()

# Debug display
st.caption(f"🛠️ Debug: Loaded {len(all_rooms)} classrooms. Ignored {len(lab_rooms)} lab/locked rooms.")

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
