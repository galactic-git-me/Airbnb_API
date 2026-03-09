import imaplib
import email
import re
import os
import requests
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_ENDPOINT = "http://localhost:7777/api/new_booking"

def decode_mime_words(s):
    if not s:
        return ""
    return u"".join(
        word.decode(encoding or "utf8") if isinstance(word, bytes) else word
        for word, encoding in decode_header(s)
    )

def parse_airbnb_email(raw_email):
    msg = email.message_from_bytes(raw_email)
    
    subject = decode_mime_words(msg.get("Subject", "")).replace('\r', '').replace('\n', '')
    if "Reservation confirmed" not in subject:
        return None # Skip unrelated emails

    date_header = msg.get("Date", "")
    try:
        email_date = parsedate_to_datetime(date_header)
        year = email_date.year
    except Exception:
        year = datetime.now().year
        
    # Get email body
    body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            try:
                content = payload.decode('utf-8', errors='ignore')
                if content_type == "text/plain":
                    body += content
                elif content_type == "text/html":
                    html_body += content
            except Exception:
                pass
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode('utf-8', errors='ignore')
    
    # Use HTML body if text body is empty (naive approach, but helps with ID extraction)
    if not body.strip() and html_body:
        # Strip HTML tags for regex matching
        body = re.sub(r'<[^>]+>', ' ', html_body)

    # Debug: Print first 100 chars of body if ID not found later
    debug_body_start = body.strip()[:100]

    # Name
    # Try multiple patterns for name
    name_match = re.search(r"Reservation confirmed - (.*?)\s+arrives", subject)
    if not name_match:
        name_match = re.search(r"New booking confirmed!\s+(.*?)\s+arrives", body)
    
    full_name = name_match.group(1).strip() if name_match else "Unknown"

    # Extraction
    # ID: Try multiple ID locations
    code_match = re.search(r"Confirmation code\s*([A-Z0-9]{10})", body, re.IGNORECASE)
    if not code_match:
        code_match = re.search(r"HM[A-Z0-9]{8}", body) # Try pattern HM...
    booking_id = code_match.group(1).strip() if code_match and len(code_match.groups()) > 0 else (code_match.group(0) if code_match else "UNKNOWN_ID")

    # Dates
    # Pattern 1: Multi-line match from body (best chance)
    arrive_date = ""
    cin_m = re.search(r"(?:Check-in|Check in|Arriving)\s*([A-Za-z]{3}, [A-Za-z]{3} \d{1,2})", body, re.IGNORECASE)
    if cin_m:
        arrive_date = f"{cin_m.group(1)} {year}"
    else:
        # Fallback to Subject: "... arrives May 2"
        cin_subj = re.search(r"arrives\s+([A-Za-z]{3}\s+\d{1,2})", subject, re.IGNORECASE)
        if cin_subj:
            arrive_date = f"{cin_subj.group(1)} {year}"

    depart_date = ""
    cout_m = re.search(r"(?:Checkout|Check-out|Check out|Departing)\s*([A-Za-z]{3}, [A-Za-z]{3} \d{1,2})", body, re.IGNORECASE)
    if cout_m:
        depart_date = f"{cout_m.group(1)} {year}"

    # Secondary range check in body: "May 2 – 3, 2026" or similar
    if not arrive_date or not depart_date:
        range_m = re.search(r"([A-Za-z]{3} \d{1,2})\s*–\s*(\d{1,2})", body)
        if range_m and not arrive_date:
            arrive_date = f"{range_m.group(1)} {year}"
    
    # Times (more lenient searching)
    check_in_time = ""
    tin_m = re.search(r"(?:Check-in|Check in|Arriving).*?(\d{1,2}:\d{2}\s*(?:AM|PM| PM| AM))", body, re.IGNORECASE | re.DOTALL)
    if tin_m:
        check_in_time = tin_m.group(1).strip()

    check_out_time = ""
    tout_m = re.search(r"(?:Checkout|Check-out|Check out|Departing).*?(\d{1,2}:\d{2}\s*(?:AM|PM| PM| AM))", body, re.IGNORECASE | re.DOTALL)
    if tout_m:
        check_out_time = tout_m.group(1).strip()

    # Total Cost
    paid_match = re.search(r"Total \(GBP\)\s*(£[0-9,\.]+)", body)
    if not paid_match:
        paid_match = re.search(r"(£[0-9,\.]+)", body)
    
    if paid_match:
        try:
            cost = paid_match.group(1).strip()
        except IndexError:
            cost = paid_match.group(0).strip()
    else:
        cost = ""

    # Guests
    guests_match = re.search(r"(\d+) adults?", body)
    adults = int(guests_match.group(1)) if guests_match else 1
    
    # Calculate nights
    nights = 1
    if arrive_date and depart_date:
        try:
            cin = datetime.strptime(arrive_date, "%a, %b %d %Y")
            cout = datetime.strptime(depart_date, "%a, %b %d %Y")
            nights = (cout - cin).days 
        except Exception:
            pass

    payload = {
        "ID": booking_id,
        "GUEST:NAME": full_name,
        "INQUIRY:ARRIVE": arrive_date,
        "INQUIRY:DEPART": depart_date,
        "INQUIRY:CHECK_IN": check_in_time,
        "INQUIRY:CHECK_OUT": check_out_time,
        "INQUIRY:COST": cost,
        "INQUIRY:NIGHTS": str(nights),
        "INQUIRY:ADULTS": str(adults),
        "INQUIRY:CHILDREN": "0",
        "INQUIRY:CHANNEL": "Airbnb",
    }
    return payload

def send_to_api(payload):
    print(f"Sending booking {payload['ID']} for {payload['GUEST:NAME']}...")
    try:
        response = requests.post(API_ENDPOINT, json=[payload])
        if response.status_code == 200:
            print(" -> Success!", response.json())
        else:
            print(" -> Failed:", response.status_code, response.text)
    except Exception as e:
        print(" -> Error:", e)

def main():
    print("=== Airbnb Email Importer ===")
    
    # Try to get credentials from .env
    email_address = os.getenv("GMAIL_ADDRESS", "dots.trading.bots@gmail.com")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not password:
        print("Error: GMAIL_APP_PASSWORD not found in .env file.")
        print("Please add 'GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx' to your .env file.")
        return

    print(f"Connecting to {email_address} using App Password...")

    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com')
        M.login(email_address, password)
    except Exception as e:
        print("Failed to login. Ensure you are using an APP PASSWORD and IMAP is enabled in Gmail settings.")
        print(f"Error details: {e}")
        return

    print("Logged in successfully. Searching inbox...")
    status, messages = M.select('INBOX')
    
    # "since 01/12/2025" IMAP date format is "01-Dec-2025"
    search_date = "01-Dec-2025"
    status, response = M.search(None, f'(SINCE "{search_date}" SUBJECT "Reservation confirmed")')
    
    email_ids = response[0].split()
    print(f"Found {len(email_ids)} emails matching criteria since {search_date}.")
    
    parsed_count = 0
    for uid in email_ids:
        status, msg_data = M.fetch(uid, '(RFC822)')
        raw_email = msg_data[0][1]
        
        payload = parse_airbnb_email(raw_email)
        if payload:
            # If ID is unknown, generate a stable fallback ID based on name and date
            # This helps the API internal logic without relying on the specific Airbnb ID format
            if payload["ID"] == "UNKNOWN_ID":
                # Create a simple stable hash-like string from name and arrival date
                name_part = payload["GUEST:NAME"].replace(" ", "")[:5].upper()
                date_part = payload["INQUIRY:ARRIVE"].replace(" ", "").replace(",", "")
                payload["ID"] = f"EML_{name_part}_{date_part}"
            
            parsed_count += 1
            print(f"\n[{parsed_count}] Email UID {uid.decode()}: Processing {payload['GUEST:NAME']} ({payload['ID']})")
            print(f"   Dates: {payload['INQUIRY:ARRIVE']} - {payload['INQUIRY:DEPART']}")
            print(f"   Cost:  {payload['INQUIRY:COST']}")
            send_to_api(payload)
        else:
            print(f"Skipping email {uid.decode()}: Subject mismatch or unparseable")
            
    print(f"\nDone! Sent {parsed_count} booking updates to the API.")
    M.logout()

if __name__ == "__main__":
    main()
