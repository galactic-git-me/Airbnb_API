import os
import json
import re
import ast
import time
import random
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'serviceaccount.json'
SPREADSHEET_ID = '14mPOQyJn2SrVQVCq853Jw3VDYuwUymqsuy7m371svgU'
SHEET_NAME = 'API_RAWRAW'
START_ROW = 287

def get_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Credentials file {SERVICE_ACCOUNT_FILE} not found.")
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def format_date_standard(date_str):
    if not date_str: return ""
    date_str = str(date_str).strip()
    try:
        # Pre-process: remove extra spaces and common punctuation
        clean = date_str.replace(",", "").replace(".", "").replace(" ", " ")
        
        # ISO format check (e.g. 2026-03-09T18:40:30.000Z)
        if "T" in date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%a %b %d, %Y")
            except: pass

        # Try various parsing formats
        for fmt in ["%a %b %d %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%a %b %d %Y %H:%M:%S", "%b %p %d %Y"]:
            try:
                dt = datetime.strptime(clean, fmt)
                return dt.strftime("%a %b %d, %Y")
            except: continue
            
        # Fallback for "May 2 2026"
        m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})", clean)
        if m:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y")
            return dt.strftime("%a %b %d, %Y")
    except: pass
    return date_str

def format_time_standard(time_str):
    if not time_str: return ""
    time_str = str(time_str).strip().upper().replace(" ", " ") # Handle thin space
    try:
        for fmt in ["%I:%M %p", "%H:%M", "%H:%M:%S", "%I:%M %p"]:
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.strftime("%-I:%M %p")
            except: continue
    except: pass
    return time_str

def parse_payload(json_str):
    if not json_str: return {}
    json_str = str(json_str).strip()
    try:
        # Try JSON first
        return json.loads(json_str.replace("'", '"'))
    except:
        try:
            # Try Python literal eval
            return ast.literal_eval(json_str)
        except:
            # Regex extraction for key fields
            res = {}
            for key in ["GUEST:SOURCE", "INQUIRY:CHANNEL", "platform", "INQUIRY:BOOK_DATE", "INQUIRY:ARRIVE", "INQUIRY:DEPART", "INQUIRY:NIGHTS", "INQUIRY:COST", "INQUIRY:CHECK_IN"]:
                m = re.search(f"['\"]{key}['\"]:\\s*['\"]([^'\"]*)['\"]", json_str)
                if m: res[key] = m.group(1)
            return res

def cleanup():
    print(f"Starting cleanup from row {START_ROW}...")
    service = get_service()
    sheet = service.spreadsheets()
    
    # Read data
    range_name = f'{SHEET_NAME}!A{START_ROW}:V'
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    values = result.get('values', [])
    
    if not values:
        print("No data found to process.")
        return

    updates = []
    for i, row in enumerate(values):
        current_row_idx = i + START_ROW
        
        # Standardize length (A to V = 22 columns)
        while len(row) < 22:
            row.append("")
            
        json_str = row[3] if len(row) > 3 else ""
        payload = parse_payload(json_str)
        
        # 1. Source (Col J / Index 9)
        source = payload.get("GUEST:SOURCE") or payload.get("INQUIRY:CHANNEL") or payload.get("platform") or ""
        if source:
            row[9] = source

        # 2. Dates (M, O, U)
        # Depart Date (Col O / Index 14)
        depart_val = row[14] or payload.get("INQUIRY:DEPART")
        row[14] = format_date_standard(depart_val)
        
        # Nights (Col Q / Index 16)
        try:
            nights_val = row[16] or payload.get("INQUIRY:NIGHTS") or 0
            nights = int(float(str(nights_val).strip()))
        except: 
            nights = 0
        
        # Arrive Date (Col M / Index 12)
        # If blank, calculate: Depart - Nights
        if (not row[12] or row[12] == "") and row[14] and nights > 0:
            try:
                dt_out = datetime.strptime(row[14], "%a %b %d, %Y")
                dt_in = dt_out - timedelta(days=nights)
                row[12] = dt_in.strftime("%a %b %d, %Y")
            except:
                row[12] = format_date_standard(row[12] or payload.get("INQUIRY:ARRIVE"))
        else:
            row[12] = format_date_standard(row[12] or payload.get("INQUIRY:ARRIVE"))

        # 3. Times (N and P)
        row[13] = format_time_standard(row[13] or payload.get("INQUIRY:CHECK_IN") or "3:00 PM")
        row[15] = "10:00 AM" # Force for all as requested

        # 4. Booking Date (Col U / Index 20)
        book_date_str = row[20] or payload.get("INQUIRY:BOOK_DATE")
        if (not book_date_str or book_date_str == "") and len(row) > 1 and row[1]:
            # Fallback to received timestamp in Col B
            book_date_str = row[1]
        row[20] = format_date_standard(book_date_str)

        # 5. Cost (Col V / Index 21)
        cost_val = row[21] or payload.get("INQUIRY:COST")
        if cost_val:
            cost_str = str(cost_val).replace("Â£", "£").replace("GBP", "").strip()
            if not cost_str.startswith("£") and re.search(r"\d", cost_str):
                cost_str = f"£{cost_str}"
            row[21] = cost_str

        updates.append(row)

    # Write back in one batch
    if updates:
        body = {'values': updates}
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID, 
            range=f'{SHEET_NAME}!A{START_ROW}:V', 
            valueInputOption='RAW', 
            body=body
        ).execute()
        print(f"Successfully cleaned up {len(updates)} rows.")
    
if __name__ == "__main__":
    try:
        cleanup()
    except Exception as e:
        print(f"An error occurred: {e}")
