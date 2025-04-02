from flask import Flask, request
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load .env file
load_dotenv()
app = Flask(__name__)

# ---------------- Zoho API Credentials ----------------
ZOHO_CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

# ---------------- Allowed Dropdown Values ----------------
ALLOWED_PIPELINES = [
    "Standard(Standard)",
    "HFS - CX pipeline",
    "HFS - Altalease",
    "Moneste"
]

ALLOWED_STAGES = [
    "HFS Initial Email and Engagement",
    "HFS Filtration",
    "HFS Prelimary Data Collection",
    "HFS Preliminary Assement",
    "HFS Application Pre-Approval",
    "HFS - Non-Binding Contract Issued",
    "HFS - Contract terms approved",
    "HFS - Credit Risk Assessment",
    "HFS - Operational DD",
    "HFS KYC/KYB",
    "HFS Security Mechanism - Initiated",
    "HFS Security Mechanism - Done",
    "HFS CFO Meeting - Done",
    "HFS Final Review",
    "On Hold",
    "HFS - Contract won & Funds deployed",
    "Cold - Lead",
    "Closed Lost",
    "Risk Assessment Failed",
    "Closed-Lost to Competition",
    "Current KPIs not fit"
]

def validate_dropdown(value, allowed_list):
    for option in allowed_list:
        if value.strip().lower() == option.lower():
            return option
    return None

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

# ---------------- Add Contact ----------------
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

# ---------------- Create Deal ----------------
def create_deal(deal_name, account_name, stage, pipeline):
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
            "Pipeline": pipeline,
            "Closing_Date": closing_date
        }]
    }
    response = requests.post("https://www.zohoapis.com/crm/v2/Deals", headers=headers, json=deal_data)
    return response.json()

# ---------------- WhatsApp Messaging ----------------
def send_whatsapp_message(to, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = {
        "From": TWILIO_NUMBER,
        "To": to,
        "Body": body
    }
    response = requests.post(url, data=data, auth=auth)

    print("📤 Twilio Message Send Response:")
    print(response.status_code)
    print(response.text)

# ---------------- Command Handler ----------------
def handle_command(message, sender):
    original_message = message.strip()
    message = original_message.lower()

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

    elif "create deal" in message:
        try:
            send_whatsapp_message(sender,
                "📝 Please send the deal in this format:\n"
                "@bot deal name DEAL_NAME account ACCOUNT_NAME stage STAGE pipeline PIPELINE_NAME\n\n"
                "📋 Available Pipelines:\n" +
                "\n".join(ALLOWED_PIPELINES) +
                "\n\n📅 Available Stages:\n" +
                "\n".join(ALLOWED_STAGES)
            )
        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error prompting for deal info: {str(e)}")

    elif all(x in message for x in ["deal name", "account", "stage", "pipeline"]):
        try:
            parts = original_message.split("deal name", 1)[1].strip()
            deal_part, rest = parts.split("account", 1)
            account_part, stage_pipeline = rest.split("stage", 1)
            stage_part, pipeline_part = stage_pipeline.split("pipeline", 1)

            deal_name = deal_part.strip()
            account_name = account_part.strip()
            stage_input = stage_part.strip()
            pipeline_input = pipeline_part.strip()

            stage = validate_dropdown(stage_input, ALLOWED_STAGES)
            pipeline = validate_dropdown(pipeline_input, ALLOWED_PIPELINES)

            if not stage:
                send_whatsapp_message(sender, "❌ Invalid stage. Available options:\n" + "\n".join(ALLOWED_STAGES))
                return

            if not pipeline:
                send_whatsapp_message(sender, "❌ Invalid pipeline. Available options:\n" + "\n".join(ALLOWED_PIPELINES))
                return

            result = create_deal(deal_name, account_name, stage, pipeline)
            if "data" in result:
                send_whatsapp_message(sender, f"✅ Deal *{deal_name}* created for account *{account_name}* in stage *{stage}*, pipeline *{pipeline}*.")
            else:
                send_whatsapp_message(sender, f"⚠️ Failed to create deal. Response: {json.dumps(result)}")

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while creating deal: {str(e)}")

    else:
        send_whatsapp_message(sender,
            "⚠️ Invalid command. Try:\n"
            "@bot add contact NAME company COMPANY\n"
            "@bot create deal"
        )

# ---------------- Webhook ----------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    message = request.form.get("Body")
    sender = request.form.get("From")
    print("🟢 Incoming WhatsApp message:", message)
    print("👤 From:", sender)
    if message and message.lower().startswith("@bot"):
        handle_command(message, sender)
    return "OK", 200

# ---------------- Run Server ----------------
if __name__ == "__main__":
    app.run(port=8000)
