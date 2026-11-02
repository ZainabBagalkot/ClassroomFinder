import streamlit as st
import csv
import os
import re
from datetime import datetime

st.set_page_config(page_title="Classroom Finder", page_icon="🏫", layout="centered")
st.title("🏫 Empty Classroom Finder")

CSV_FILE = "2026-2027 Schedule - Fall 2026.csv"
MANUAL_LAB_FILE = "manual_lab_rooms"

DAY_START = 8 * 60
DAY_END = 21 * 60

def clean_room_name(r):
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

@st.cache_data
def load_data():
    room_day = {}
    # Dictionary to hold room statuses (e.g., {"D002": "Office", "D015": "Lab"})
    room_statuses = {}
    
    if os.path.exists(MANUAL_LAB_FILE):
        with open(MANUAL_LAB_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Split the line by space. The first part is the room, the rest is the status.
                parts = line.split(maxsplit=1)
                room_raw = parts[0]
                room_clean = clean_room_name(room_raw)
                
                # Save the status (e.g., "office" or "lab"). If no status, default to "Locked/Lab"
                status = parts[1].capitalize() if len(parts) > 1 else "Locked / Lab"
                room_statuses[room_clean] = status

    if not os.path.exists(CSV_FILE):
        st.error(f"Error: Could not find the CSV file at {CSV_FILE}")
        return {}, {}

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = None
        for row in reader:
            if row and "Room #" in row:
                headers = row
                break
                
        if not headers: return {}, {}

        r_idx, d_idx, s_idx, e_idx = headers.index("Room #"), headers.index("Days"), headers.index("Time Start"), headers.index("Time End")
        c_idx = headers.index("Course Name")

        for row in reader:
            if len(row) <= max(r_idx, d_idx, s_idx, e_idx): continue
            
            room_raw = row[r_idx].strip()
            room_clean = clean_room_name(room_raw)
            
            if not room_raw or ' ' in room_raw or room_raw.upper().startswith("TBD"): continue
            
            start, end = to_min(row[s_idx]), to_min(row[e_idx])
            if start is None or end is None: continue

            days = set()
            ds = row[d_idx].upper()
            if "M" in ds: days.add("Mon")
            if "T" in ds: days.add("Tue")
            if "W" in ds: days.add("Wed")
            if "R" in ds: days.add("Thu")
            if "F" in ds: days.add("Fri")
            
            course_name = row[c_idx].strip()
            
            for d in days:
                room_day.setdefault(room_raw, {}).setdefault(d, []).append((start, end, course_name))
                
    return room_day, room_statuses

room_day, room_statuses = load_data()

# Build the list of allowed classrooms
all_rooms = []
for r in room_day.keys():
    if clean_room_name(r) not in room_statuses:
        all_rooms.append(r)
all_rooms = sorted(all_rooms)

if not room_day:
    st.stop()

# --- APP NAVIGATION ---
tab1, tab2 = st.tabs(["🔍 Find Free Rooms", "🔎 Lookup Room"])

with tab1:
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
                
                intervals = sorted(room_day[room].get(selected_day, []))
                
                merged = []
                for s, e, c in intervals:
                    if not merged or s > merged[-1][1]:
                        merged.append([s, e, c])
                    else:
                        merged[-1][1] = max(merged[-1][1], e)
                        
                gaps = []
                cur = DAY_START
                for i, (s, e, c) in enumerate(merged):
                    if s > cur:
                        gaps.append((cur, s, c))
                    cur = max(cur, e)
                    
                if cur < DAY_END:
                    gaps.append((cur, DAY_END, "No more classes"))

                for gs, ge, next_class in gaps:
                    if gs <= req_start and req_end <= ge:
                        results.append({
                            "Room": room, 
                            "Free From": fmt(gs), 
                            "Free Until": fmt(ge),
                            "Next Class": next_class
                        })
                        break

            if results:
                st.success(f"Found {len(results)} free rooms on {selected_day}!")
                st.dataframe(results, use_container_width=True, hide_index=True)
            else:
                st.warning("No classrooms are completely free during this time.")

with tab2:
    st.subheader("Room Lookup")
    search_room = st.text_input("Enter a room number (e.g., D114 or D002):").strip()
    
    if search_room:
        clean_search = clean_room_name(search_room)
        
        # 1. Check if the room is in the manual list (Office, Lab, etc.)
        if clean_search in room_statuses:
            status = room_statuses[clean_search]
            st.info(f"**{search_room.upper()}** - {status}")
            
        # 2. Check if the room is a known classroom from the CSV
        elif any(clean_room_name(r) == clean_search for r in room_day.keys()):
            # Find the actual room name formatting used in the CSV
            actual_name = next(r for r in room_day.keys() if clean_room_name(r) == clean_search)
            st.success(f"**{actual_name}** - Classroom")
            
        # 3. Not found at all
        else:
            st.error("Room not found in the schedule or manual list.")
