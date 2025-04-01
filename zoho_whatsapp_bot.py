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
    """Exchange refresh token for an access token"""
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
    """Add a contact to Zoho CRM"""
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

# ---------------- Find Contact in Zoho CRM ----------------
def find_contact(name, company):
    """Search for a contact by last name and account name"""
    access_token = get_access_token()
    last_name = name.split()[-1]
    url = f"https://www.zohoapis.com/crm/v2/Contacts/search?criteria=(Last_Name:equals:{last_name})and(Account_Name:equals:{company})"
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    if "data" in data:
        return data["data"][0]
    return None

# ---------------- Convert Contact to Deal ----------------
def convert_to_deal(custom_deal_name, company, stage="Initial Stage"):
    """
    Convert a contact (if exists) into a deal, or just associate the deal with a company.
    Returns a message to send back to the user.
    """
    try:
        contact = find_contact(custom_deal_name, company)
        contact_id = contact["id"] if contact else None

        access_token = get_access_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json"
        }

        deal_name = f"{company} {custom_deal_name}"

        deal_data = {
            "Deal_Name": deal_name,
            "Stage": stage,
            "Account_Name": company
        }

        if contact_id:
            deal_data["Contact_Name"] = {"id": contact_id}

        payload = {"data": [deal_data]}
        response = requests.post("https://www.zohoapis.com/crm/v2/Deals", headers=headers, json=payload)
        res_data = response.json()

        if response.status_code == 201:
            if contact_id:
                return f"✅ Deal *'{deal_name}'* successfully created in stage *{stage}*, linked to the contact."
            else:
                return f"✅ Deal *'{deal_name}'* created in stage *{stage}*. No contact was linked, only the company."
        elif "data" in res_data and "message" in res_data["data"][0]:
            return f"⚠️ Failed to create deal: {res_data['data'][0]['message']}"
        else:
            return f"⚠️ Failed to create deal. Response: {json.dumps(res_data)}"

    except Exception as e:
        return f"❌ Internal error occurred while creating deal: {str(e)}"


# ---------------- Send WhatsApp Message ----------------
def send_whatsapp_message(to, body):
    """Reply to the user via WhatsApp using Twilio"""
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = {
        "From": TWILIO_NUMBER,
        "To": to,
        "Body": body
    }
    requests.post(url, data=data, auth=auth)

# ---------------- Handle Incoming WhatsApp Commands ----------------
def handle_command(message, sender):
    """Parse the message and route to appropriate Zoho action"""
    message = message.strip()

    # ---------------- Handle Add Contact ----------------
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

    # ---------------- Handle Convert to Deal ----------------
    elif "convert" in message and "to a deal" in message:
        try:
            between_convert_to = message.split("convert", 1)[1].split("to a deal", 1)[0].strip()
            words = between_convert_to.split()

            if len(words) < 2:
                send_whatsapp_message(sender, "⚠️ Please provide both a deal identifier and a company name.")
                return

            custom_name = words[0]
            company = " ".join(words[1:])

            stage = message.split(" in ", 1)[1].strip() if " in " in message else "Initial Stage"

            result = convert_to_deal(custom_name, company, stage)
            send_whatsapp_message(sender, result)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while converting to deal: {str(e)}")

    # ---------------- Handle Create Deal ----------------
    elif "create deal with" in message and "as the account name" in message and "as the deal name" in message:
        try:
            account_part = message.split("create deal with", 1)[1].split("as the account name", 1)[0].strip()
            deal_part = message.split("as the deal name", 1)[1].strip()

            account = account_part
            deal_name = deal_part
            stage = "Initial Stage"

            result = convert_to_deal(deal_name, account, stage)
            send_whatsapp_message(sender, result)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while creating deal: {str(e)}")

    # ---------------- Invalid Format ----------------
    else:
        send_whatsapp_message(
            sender,
            "⚠️ Invalid command format. Use:\n"
            "@bot add contact NAME company COMPANY\n"
            "@bot convert DEAL_ID COMPANY to a deal in STAGE\n"
            "@bot create deal with ACCOUNT_NAME as the account name and this as the deal name DEAL_NAME"
        )



# ---------------- Flask Route for WhatsApp Webhook ----------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    """Receives WhatsApp message and triggers command handling"""
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
