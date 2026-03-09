import re
import email
from datetime import datetime

email_body = """
Check-in

Sat, May 2

3:00 PM
	

Checkout

Sun, May 3

10:00 AM
Guests

2 adults
More details about who’s coming

Guests will now let you know if they’re bringing children and infants. Let them know upfront if your listing is suitable for children by updating your House Rules.
Confirmation code

HMRYFP442M
	
View itinerary
Guest paid

£137.55 x 1 night
	

£137.55

Guest service fee
	

£0.00
Total (GBP)
	
£137.55
"""

def test_parse():
    year = 2026

    # Confirmation code
    code_match = re.search(r"Confirmation code\s*([A-Z0-9]{10})", email_body)
    booking_id = code_match.group(1).strip() if code_match else "UNKNOWN_ID"
    print("ID:", booking_id)

    # Dates
    checkin_match = re.search(r"Check-in\s*([A-Za-z]{3}, [A-Za-z]{3} \d{1,2})", email_body)
    print(checkin_match)
    if checkin_match:
        arrive_str = checkin_match.group(1) # Sat, May 2
        arrive_date = f"{arrive_str} {year}"
    else:
        arrive_date = ""
    print("Arrive:", arrive_date)

    checkout_match = re.search(r"Checkout\s*([A-Za-z]{3}, [A-Za-z]{3} \d{1,2})", email_body)
    if checkout_match:
        depart_str = checkout_match.group(1)
        depart_date = f"{depart_str} {year}"
    else:
        depart_date = ""
    print("Depart:", depart_date)

    # Times
    checkin_time_match = re.search(r"Check-in\s*[A-Za-z]{3}, [A-Za-z]{3} \d{1,2}\s*(\d{1,2}:\d{2}\s*[APap][Mm]?)", email_body)
    check_in_time = checkin_time_match.group(1).strip() if checkin_time_match else ""
    print("Check-in Time:", check_in_time)

    checkout_time_match = re.search(r"Checkout\s*[A-Za-z]{3}, [A-Za-z]{3} \d{1,2}\s*(\d{1,2}:\d{2}\s*[APap][Mm]?)", email_body)
    check_out_time = checkout_time_match.group(1).strip() if checkout_time_match else ""
    print("Check-out Time:", check_out_time)

    # Total Cost
    paid_match = re.search(r"Total \(GBP\)\s*(£[\d\.]+)", email_body)
    if not paid_match:
        paid_match = re.search(r"£[\d\.]+", email_body)
    cost = paid_match.group(1).strip() if paid_match else ""
    print("Cost:", cost)

    # Guests
    guests_match = re.search(r"(\d+) adults?", email_body)
    adults = int(guests_match.group(1)) if guests_match else 1
    print("Adults:", adults)
    
if __name__ == "__main__":
    test_parse()
