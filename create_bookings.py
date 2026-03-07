import requests
import json

# Define the API base URL
BASE_URL = "https://studio-at-113b.duckdns.org"

# Define the booking data
bookings = [
    {
        "ID": "Catherine Connolly | 18 Oct, 2024 to 20 Oct, 2024 Airbnb",
        "GUEST_NAME": "Catherine Connolly",
        "INQUIRY_ARRIVE": "18 Oct, 2024",
        "INQUIRY_DEPART": "20 Oct, 2024",
        "INQUIRY_NIGHTS": 2,
        "INQUIRY_COST": "£206.64",
        "INQUIRY_CHANNEL": "Airbnb",
        "INQUIRY_BOOK_DATE": "09 Aug, 2024",
        "GUEST_EMAIL": "catherine.connolly@example.com",
        "GUEST_PHONE": "1234567890"
    },
    {
        "ID": "Marie Baines | 16 Aug, 2024 to 17 Aug, 2024 Airbnb",
        "GUEST_NAME": "Marie Baines",
        "INQUIRY_ARRIVE": "16 Aug, 2024",
        "INQUIRY_DEPART": "17 Aug, 2024",
        "INQUIRY_NIGHTS": 1,
        "INQUIRY_COST": "£84.31",
        "INQUIRY_CHANNEL": "Airbnb",
        "INQUIRY_BOOK_DATE": "13 Aug, 2024",
        "GUEST_EMAIL": "marie.baines@example.com",
        "GUEST_PHONE": "1234567890"
    },
    {
        "ID": "Jared Cape | 17 Aug, 2024 to 18 Aug, 2024 Airbnb",
        "GUEST_NAME": "Jared Cape",
        "INQUIRY_ARRIVE": "17 Aug, 2024",
        "INQUIRY_DEPART": "18 Aug, 2024",
        "INQUIRY_NIGHTS": 1,
        "INQUIRY_COST": "£86.40",
        "INQUIRY_CHANNEL": "Airbnb",
        "INQUIRY_BOOK_DATE": "16 Aug, 2024",
        "GUEST_EMAIL": "jared.cape@example.com",
        "GUEST_PHONE": "1234567890"
    },
    {
        "ID": "Mashud Miah | 21 Aug, 2024 to 23 Aug, 2024 Airbnb",
        "GUEST_NAME": "Mashud Miah",
        "INQUIRY_ARRIVE": "21 Aug, 2024",
        "INQUIRY_DEPART": "23 Aug, 2024",
        "INQUIRY_NIGHTS": 2,
        "INQUIRY_COST": "£138.91",
        "INQUIRY_CHANNEL": "Airbnb",
        "INQUIRY_BOOK_DATE": "20 Aug, 2024",
        "GUEST_EMAIL": "mashud.miah@example.com",
        "GUEST_PHONE": "1234567890"
    },
    {
        "ID": "Carl Churchill | 24 Aug, 2024 to 26 Aug, 2024 Airbnb",
        "GUEST_NAME": "Carl Churchill",
        "INQUIRY_ARRIVE": "24 Aug, 2024",
        "INQUIRY_DEPART": "26 Aug, 2024",
        "INQUIRY_NIGHTS": 2,
        "INQUIRY_COST": "£164.23",
        "INQUIRY_CHANNEL": "Airbnb",
        "INQUIRY_BOOK_DATE": "22 Aug, 2024",
        "GUEST_EMAIL": "carl.churchill@example.com",
        "GUEST_PHONE": "1234567890"
    },
    {
        "ID": "Nadzeya Kukhta | 28 Sep, 2024 to 05 Oct, 2024 Agoda.com",
        "GUEST_NAME": "Nadzeya Kukhta",
        "INQUIRY_ARRIVE": "28 Sep, 2024",
        "INQUIRY_DEPART": "05 Oct, 2024",
        "INQUIRY_NIGHTS": 7,
        "INQUIRY_COST": "£310.90",
        "INQUIRY_CHANNEL": "Agoda.com",
        "INQUIRY_BOOK_DATE": "26 Aug, 2024",
        "GUEST_EMAIL": "nadzeya.kukhta@example.com",
        "GUEST_PHONE": "1234567890"
    }
]

# Function to send a POST request
def send_post_request(url, payload):
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    return response.status_code, response.json()

# Send new booking requests
for booking in bookings:
    new_booking_payload = {
        "ID": booking["ID"],
        "GUEST:NAME": booking["GUEST_NAME"],
        "GUEST:EMAIL": booking["GUEST_EMAIL"],
        "GUEST:PHONE": booking["GUEST_PHONE"],
        "INQUIRY:ARRIVE": booking["INQUIRY_ARRIVE"],
        "INQUIRY:DEPART": booking["INQUIRY_DEPART"],
        "INQUIRY:NIGHTS": booking["INQUIRY_NIGHTS"],
        "INQUIRY:CHANNEL": booking["INQUIRY_CHANNEL"],
        "INQUIRY:BOOK_DATE": booking["INQUIRY_BOOK_DATE"],
        "INQUIRY:COST": booking["INQUIRY_COST"]
    }
    url = f"{BASE_URL}/api/new_booking"
    status_code, response = send_post_request(url, new_booking_payload)
    print(f"New Booking Response for {booking['GUEST_NAME']}: Status {status_code}, Response {response}")

# Send update post-booking requests
for booking in bookings:
    update_post_booking_payload = {"ID": booking["ID"]}
    url = f"{BASE_URL}/api/updatepostbooking"
    status_code, response = send_post_request(url, update_post_booking_payload)
    print(f"Update Post Booking Response for {booking['GUEST_NAME']}: Status {status_code}, Response {response}")

# Send update welcome pack requests
for booking in bookings:
    update_welcome_pack_payload = {"ID": booking["ID"]}
    url = f"{BASE_URL}/api/updatewelcomepack"
    status_code, response = send_post_request(url, update_welcome_pack_payload)
    print(f"Update Welcome Pack Response for {booking['GUEST_NAME']}: Status {status_code}, Response {response}")

# Send update post-stay requests
for booking in bookings:
    update_post_stay_payload = {"ID": booking["ID"]}
    url = f"{BASE_URL}/api/updatepoststay"
    status_code, response = send_post_request(url, update_post_stay_payload)
    print(f"Update Post Stay Response for {booking['GUEST_NAME']}: Status {status_code}, Response {response}")

