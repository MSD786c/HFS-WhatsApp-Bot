from flask import Flask, request
import requests
import json
import base64
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load .env file
load_dotenv()
# Initialize the Flask app
app = Flask(__name__)

# ---------------- Zoho API Credentials ----------------
ZOHO_CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

# ---------------- Get Zoho Access Token ----------------
def get_access_token():
    url = "https://accounts.zoho.com/oauth/v2/token"
    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, params=params)
    return response.json().get("access_token")

# ---------------- Add Contact to Zoho CRM ----------------
def add_contact(name, company):
    access_token = get_access_token()
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }
    first_name = " ".join(name.split()[:-1])
    last_name = name.split()[-1]

    data = {
        "data": [{
            "First_Name": first_name,
            "Last_Name": last_name,
            "Account_Name": company
        }]
    }
    response = requests.post("https://www.zohoapis.com/crm/v2/Contacts", headers=headers, json=data)
    return response.json()

# ---------------- Create Deal in Zoho CRM ----------------
def create_deal(deal_name, account_name, stage):
    access_token = get_access_token()
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }
    closing_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    deal_data = {
        "data": [{
            "Deal_Name": deal_name,
            "Account_Name": account_name,
            "Stage": stage,
            "Closing_Date": closing_date
        }]
    }
    response = requests.post("https://www.zohoapis.com/crm/v2/Deals", headers=headers, json=deal_data)
    return response.json()

# ---------------- Send WhatsApp Message ----------------
def send_whatsapp_message(to, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = {
        "From": TWILIO_NUMBER,
        "To": to,
        "Body": body
    }
    requests.post(url, data=data, auth=auth)

# ---------------- Handle WhatsApp Commands ----------------
def handle_command(message, sender):
    message = message.strip().lower()

    # Add Contact Command
    if "add" in message and "contact" in message and "company" in message:
        try:
            after_contact = message.split("contact", 1)[1].strip()
            name_part, company_part = after_contact.split("company", 1)
            name = name_part.strip()
            company = company_part.strip()

            if not name or not company:
                send_whatsapp_message(sender, "⚠️ Name or company is missing.")
                return

            result = add_contact(name, company)
            if "data" in result:
                send_whatsapp_message(sender, f"✅ Added contact *{name}* with company *{company}*.")
            else:
                send_whatsapp_message(sender, f"⚠️ Failed to add contact. Response: {json.dumps(result)}")

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while adding contact: {str(e)}")

    # Create Deal Prompt
    elif "create deal" in message:
        try:
            send_whatsapp_message(sender, "📝 Please send the deal in this format:\n@bot deal name DEAL_NAME account ACCOUNT_NAME stage STAGE")
        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error prompting for deal info: {str(e)}")

    # Deal Details Provided
    elif "deal name" in message and "account" in message and "stage" in message:
        try:
            parts = message.split("deal name", 1)[1].strip()
            deal_part, rest = parts.split("account", 1)
            account_part, stage_part = rest.split("stage", 1)

            deal_name = deal_part.strip()
            account_name = account_part.strip()
            stage = stage_part.strip()

            result = create_deal(deal_name, account_name, stage)
            if "data" in result:
                send_whatsapp_message(sender, f"✅ Deal *{deal_name}* created for account *{account_name}* in stage *{stage}*.")
            else:
                send_whatsapp_message(sender, f"⚠️ Failed to create deal. Response: {json.dumps(result)}")

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while creating deal: {str(e)}")

    else:
        send_whatsapp_message(sender, "⚠️ Invalid command. Try:\n@bot add contact NAME company COMPANY\n@bot create deal")

# ---------------- Flask WhatsApp Webhook ----------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    message = request.form.get("Body")
    sender = request.form.get("From")
    print("🟢 Incoming WhatsApp message:", message)
    print("👤 From:", sender)
    if message and message.lower().startswith("@bot"):
        handle_command(message, sender)
    return "OK", 200

# ---------------- Run Flask Server ----------------
if __name__ == "__main__":
    app.run(port=8000)
