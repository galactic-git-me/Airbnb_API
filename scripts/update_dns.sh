#!/bin/bash

# --- CONFIGURATION ---
# Replace these with your Dynu credentials
DYNU_USERNAME="jupiterascending"
DYNU_PASSWORD='!!Janeway1153red'
DYNU_HOSTNAME="studio-at-113b.ddnsgeek.com"
# ---------------------

echo "Updating Dynu DNS for $DYNU_HOSTNAME..."

# Calculate MD5 hash of the password for the query string
PASSWORD_MD5=$(echo -n "$DYNU_PASSWORD" | md5sum | awk '{print $1}')

# Using the format that just successfully returned 'good'
URL="http://api.dynu.com/nic/update?username=${DYNU_USERNAME}&password=${DYNU_PASSWORD}"

RESULT=$(curl -s "$URL")

echo "Result: $RESULT"

if [[ "$RESULT" == *"good"* ]] || [[ "$RESULT" == *"nochg"* ]]; then
    echo "Success: $(date)"
else
    echo "Failed: $(date)"
fi
