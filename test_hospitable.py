import requests
import json

# The local address of your API
URL = "http://localhost:7777/api/hospitable/webhook"

# Mock Hospitable payload for a Created Reservation
payload_created = {
    "action": "reservation.created",
    "data": {
        "id": "mock-uuid-1234",
        "platform": "airbnb",
        "platform_id": "MOCK_AIRBNB_ID_001",
        "booking_date": "2026-03-07T12:00:00Z",
        "arrival_date": "2026-04-01T00:00:00Z",
        "departure_date": "2026-04-05T00:00:00Z",
        "nights": 4,
        "check_in": "2026-04-01T15:00:00Z",
        "check_out": "2026-04-05T11:00:00Z",
        "guests": {
            "adults": 2,
            "children": 1
        },
        "guest": {
            "first_name": "Test",
            "last_name": "Guest",
            "email": "test@example.com",
            "phone": "+123456789",
            "country": "UK"
        },
        "financials": {
            "guest": {
                "total_price": {
                    "amount": 50000,
                    "formatted": "£500.00"
                }
            }
        }
    }
}

# Mock Hospitable payload for a Changed Reservation
payload_changed = {
    "action": "reservation.changed",
    "data": {
        "platform_id": "MOCK_AIRBNB_ID_001",
        "status": "Accepted",
        "arrival_date": "2026-04-01T00:00:00Z",
        "departure_date": "2026-04-06T00:00:00Z", # Changed date
        "nights": 5
    }
}

def send_test(payload, description):
    print(f"--- Sending {description} ---")
    try:
        response = requests.post(URL, json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("NOTE: Ensure your main.py is running on port 7777 before running this test.")
    print("Also note: This will fail with 403 unless run from a whitelisted IP OR if whitelisting is temporarily disabled for testing.")
    send_test(payload_created, "Reservation Created")
    send_test(payload_changed, "Reservation Changed")
