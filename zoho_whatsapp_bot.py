from flask import Flask, request
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from openai import OpenAI
import urllib.parse


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

# ---------------- Pending Confirmations ----------------
pending_deal_confirmations = {}
# ---------------- Available Bot Commands ----------------
BOT_COMMANDS = [
    {"command": "@bot add contact [Full Name] company [Company Name]", "description": "Add a new contact to Zoho CRM"},
    {"command": "@bot create deal", "description": "Create a new deal in Zoho CRM"},
    {"command": "@bot note [Deal Name] note_content [Your Note]", "description": "Add a note to an existing deal"},
    {"command": "@bot update deal [Deal Name] stage [Stage Name]", "description": "Update the stage of an existing deal"},
    {"command": "@bot search deal [Deal Name]", "description": "Search for a deal by name"},
    {"command": "@bot search account [Account Name]", "description": "Search for an account by name"},
    {"command": "@bot search contact [Contact Name]", "description": "Search for a contact by name"},
    {"command": "@bot help", "description": "Show this help menu"},
]
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

# ---------------- Add Note to Deal ----------------
def add_note_to_deal(deal_name, note_text):
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    # Search for deal
    search_url = f"https://www.zohoapis.com/crm/v2/Deals/search?criteria=(Deal_Name:equals:{deal_name})"
    search_response = requests.get(search_url, headers=headers)
    search_data = search_response.json()

    if "data" not in search_data:
        return f"❌ No deal found with name: {deal_name}"

    deal_id = search_data["data"][0]["id"]

    # Add the note
    note_url = f"https://www.zohoapis.com/crm/v2/Deals/{deal_id}/Notes"
    note_headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }
    note_payload = {
        "data": [
            {
                "Note_Title": "Bot Note",
                "Note_Content": note_text
            }
        ]
    }
    note_response = requests.post(note_url, headers=note_headers, json=note_payload)
    return "✅ Note added to deal." if note_response.status_code == 201 else f"❌ Failed to add note: {note_response.text}"
# ---------------- LLM Helper ----------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_llm(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are a CRM assistant. Help users add contacts, create deals, update deals, search contacts, and add notes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Error calling LLM: {str(e)}")
        return "⚠️ I'm currently unable to process that request. Please try again later."


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
    print(f"To: {to}")
    print(response.status_code)
    print(response.text)
# ---------------- Command Handler ----------------
def handle_command(message, sender):
    original_message = message.strip()
    message = original_message.lower()

    if "@bot help" in message:
        help_text = "🤖 *HFS CRM Bot Commands*\n\n"

        for cmd in BOT_COMMANDS:
            help_text += f"• *{cmd['command']}*\n  _{cmd['description']}_\n\n"

        help_text += "📋 *Tip:* Always start your message with `@bot`!"

        send_whatsapp_message(sender, help_text)
        return

    elif "add" in message and "contact" in message and "company" in message:
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

    elif "@bot create deal" in message:
        try:
            prompt_text = (
                "📝 To create a new deal, please send the details in this format:\n"
                "`deal name DEAL_NAME account ACCOUNT_NAME stage STAGE_NAME pipeline PIPELINE_NAME`\n\n"
                "📋 *Available Pipelines:*\n" +
                "\n".join(ALLOWED_PIPELINES) +
                "\n\n📋 *Available Stages:*\n" +
                "\n".join(ALLOWED_STAGES)
            )
            send_whatsapp_message(sender, prompt_text)
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

            # Save the pending deal for confirmation
            pending_deal_confirmations[sender] = {
                "deal_name": deal_name,
                "account_name": account_name,
                "stage": stage,
                "pipeline": pipeline
            }

            # Ask for confirmation
            preview = (
                f"🆕 *Deal Preview:*\n"
                f"• Deal Name: *{deal_name}*\n"
                f"• Account Name: *{account_name}*\n"
                f"• Stage: *{stage}*\n"
                f"• Pipeline: *{pipeline}*\n\n"
                "✅ Reply *yes* to confirm or *no* to cancel."
            )
            send_whatsapp_message(sender, preview)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while preparing deal: {str(e)}")

    elif "note" in message and "note_content" in message:
        try:
            parts = original_message.split("note", 1)[1].strip()
            deal_part, note_part = parts.split("note_content", 1)
            deal_name = deal_part.strip()
            note_text = note_part.strip()

            result = add_note_to_deal(deal_name, note_text)
            send_whatsapp_message(sender, result)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while adding note: {str(e)}")

    elif sender in pending_deal_confirmations:
        # Waiting for user confirmation
        user_reply = message.strip().lower()

        if user_reply == "yes":
            # User confirmed deal creation
            deal_info = pending_deal_confirmations.pop(sender)
            result = create_deal(
                deal_info["deal_name"],
                deal_info["account_name"],
                deal_info["stage"],
                deal_info["pipeline"]
            )
            if "data" in result:
                send_whatsapp_message(sender, f"✅ Deal *{deal_info['deal_name']}* created successfully!")
            else:
                send_whatsapp_message(sender, f"⚠️ Failed to create deal. Response: {json.dumps(result)}")

        elif user_reply == "no":
            # User canceled
            pending_deal_confirmations.pop(sender)
            send_whatsapp_message(sender, "❌ Deal creation cancelled.")

        else:
            # Invalid confirmation reply
            send_whatsapp_message(sender, "⚠️ Please reply with *yes* to confirm or *no* to cancel.")
    elif "@bot update deal" in message and "stage" in message:
        try:
            parts = original_message.split("update deal", 1)[1].strip()
            deal_part, stage_part = parts.split("stage", 1)

            deal_name = deal_part.strip()
            stage_input = stage_part.strip()

            stage = validate_dropdown(stage_input, ALLOWED_STAGES)

            if not stage:
                send_whatsapp_message(sender, "❌ Invalid stage. Available options:\n" + "\n".join(ALLOWED_STAGES))
                return

            # Search for the deal by name
            access_token = get_access_token()
            search_url = f"https://www.zohoapis.com/crm/v2/Deals/search?criteria=(Deal_Name:equals:{deal_name})"
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            response = requests.get(search_url, headers=headers)
            data = response.json()

            if "data" not in data:
                send_whatsapp_message(sender, f"❌ No deal found with name: {deal_name}")
                return

            deal_id = data["data"][0]["id"]

            # Update deal's stage
            update_url = f"https://www.zohoapis.com/crm/v2/Deals/{deal_id}"
            update_payload = {
                "data": [
                    {
                        "Stage": stage
                    }
                ]
            }
            update_headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            }
            update_response = requests.put(update_url, headers=update_headers, json=update_payload)

            if update_response.status_code == 200:
                send_whatsapp_message(sender, f"✅ Deal *{deal_name}* updated to stage *{stage}* successfully!")
            else:
                send_whatsapp_message(sender, f"⚠️ Failed to update deal. Response: {json.dumps(update_response.json())}")

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while updating deal stage: {str(e)}")


    elif "@bot search contact" in message:
        try:
            contact_query = original_message.split("search contact", 1)[1].strip()

            if not contact_query:
                send_whatsapp_message(sender, "⚠️ Please provide a contact name to search.")
                return

            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

            # Try exact match on Full_Name first
            criteria_raw = f"(Full_Name:equals:{contact_query})"
            criteria_encoded = urllib.parse.quote(criteria_raw, safe="():")
            search_url = f"https://www.zohoapis.com/crm/v2/Contacts/search?criteria={criteria_encoded}"

            print(f"🔍 Searching Contact with URL: {search_url}")
            response = requests.get(search_url, headers=headers)
            data = response.json()

            if "data" not in data or not data["data"]:
                # Fallback to partial match on First/Last/Full name
                words = contact_query.split()
                criteria_parts = []
                for word in words:
                    criteria_parts.append(f"(First_Name:contains:{word})")
                    criteria_parts.append(f"(Last_Name:contains:{word})")
                    criteria_parts.append(f"(Full_Name:contains:{word})")
                criteria_raw = "(" + " or ".join(criteria_parts) + ")"
                criteria_encoded = urllib.parse.quote(criteria_raw, safe="():")
                search_url = f"https://www.zohoapis.com/crm/v2/Contacts/search?criteria={criteria_encoded}"

                print(f"🔍 Fallback Searching Contact with URL: {search_url}")
                response = requests.get(search_url, headers=headers)
                data = response.json()

            if "data" not in data or not data["data"]:
                send_whatsapp_message(sender, f"❌ No contact found matching: {contact_query}")
                return

            contact = data["data"][0]
            first_name = contact.get("First_Name", "N/A")
            last_name = contact.get("Last_Name", "N/A")
            company = contact.get("Account_Name", {}).get("name", "N/A")
            email = contact.get("Email", "N/A")
            phone = contact.get("Phone", "N/A")

            contact_info = (
                f"👤 *Contact Found:*\n"
                f"• Name: *{first_name} {last_name}*\n"
                f"• Company: *{company}*\n"
                f"• Email: *{email}*\n"
                f"• Phone: *{phone}*"
            )
            send_whatsapp_message(sender, contact_info)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while searching for contact: {str(e)}")

    elif "@bot search deal" in message:
        try:
            deal_query = original_message.split("search deal", 1)[1].strip()

            if not deal_query:
                send_whatsapp_message(sender, "⚠️ Please provide a deal name to search.")
                return

            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

            # Try exact match first
            criteria_raw = f"(Deal_Name:equals:{deal_query})"
            criteria_encoded = urllib.parse.quote(criteria_raw, safe="():")
            search_url = f"https://www.zohoapis.com/crm/v2/Deals/search?criteria={criteria_encoded}"

            print(f"🔍 Searching Deal with URL: {search_url}")
            response = requests.get(search_url, headers=headers)
            data = response.json()

            if "data" not in data or not data["data"]:
                # Fallback to partial match
                criteria_raw = f"(Deal_Name:contains:{deal_query})"
                criteria_encoded = urllib.parse.quote(criteria_raw, safe="():")
                search_url = f"https://www.zohoapis.com/crm/v2/Deals/search?criteria={criteria_encoded}"
                response = requests.get(search_url, headers=headers)
                data = response.json()

            if "data" not in data or not data["data"]:
                send_whatsapp_message(sender, f"❌ No deal found matching: {deal_query}")
                return

            deal = data["data"][0]
            name = deal.get("Deal_Name", "N/A")
            account = deal.get("Account_Name", {}).get("name", "N/A")
            stage = deal.get("Stage", "N/A")
            pipeline = deal.get("Pipeline", "N/A")
            amount = deal.get("Amount", "N/A")
            closing = deal.get("Closing_Date", "N/A")

            deal_info = (
                f"🔍 *Deal Found:*\n"
                f"• Name: *{name}*\n"
                f"• Account: *{account}*\n"
                f"• Stage: *{stage}*\n"
                f"• Pipeline: *{pipeline}*\n"
                f"• Amount: *{amount}*\n"
                f"• Closing Date: *{closing}*"
            )
            send_whatsapp_message(sender, deal_info)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while searching for deal: {str(e)}")

    elif "@bot search account" in message:
        try:
            account_query = original_message.split("search account", 1)[1].strip()

            if not account_query:
                send_whatsapp_message(sender, "⚠️ Please provide an account name to search.")
                return

            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

            # Split into words for flexible matching (case-sensitive in Zoho!)
            words = account_query.split()
            criteria_parts = [f"(Account_Name:contains:{word})" for word in words]
            criteria_raw = "(" + " or ".join(criteria_parts) + ")"
            encoded_criteria = urllib.parse.quote(criteria_raw)

            search_url = f"https://www.zohoapis.com/crm/v2/Accounts/search?word={urllib.parse.quote(account_query)}"
            response = requests.get(search_url, headers=headers)
            data = response.json()

            if "data" not in data or not data["data"]:
                send_whatsapp_message(sender, f"❌ No account found matching: {account_query}")
                return

            # Return first match
            account = data["data"][0]
            name = account.get("Account_Name", "N/A")
            phone = account.get("Phone", "N/A")
            website = account.get("Website", "N/A")
            industry = account.get("Industry", "N/A")
            account_id = account.get("id", "N/A")

            account_details = (
                f"🏢 *Account Found:*\n"
                f"• Name: *{name}*\n"
                f"• Phone: *{phone}*\n"
                f"• Website: *{website}*\n"
                f"• Industry: *{industry}*\n"
                f"• ID: `{account_id}`"
            )

            send_whatsapp_message(sender, account_details)

        except Exception as e:
            send_whatsapp_message(sender, f"❌ Error while searching for account: {str(e)}")
    else:
        send_whatsapp_message(sender,
            "⚠️ Invalid command. Try:\n"
            "@bot add contact NAME company COMPANY\n"
            "@bot create deal\n"
            "@bot note DEAL_NAME note_content YOUR_NOTE"
        )
# ---------------- Webhook ----------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    message = request.form.get("Body")
    sender = request.form.get("From")
    print("🟢 Incoming WhatsApp message:", message)
    print("👤 From:", sender)

    # 🔥 First: Check if the user has pending confirmation
    if sender in pending_deal_confirmations:
        handle_command(message, sender)
    elif message and message.lower().startswith("@bot"):
        handle_command(message, sender)
    else:
        # No pending confirmation, no @bot → Use LLM
        llm_response = ask_llm(message)
        send_whatsapp_message(sender, llm_response)

    return "OK", 200

@app.route("/debug/deals")
def debug_deals():
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    response = requests.get("https://www.zohoapis.com/crm/v2/Deals", headers=headers)
    return response.json()

@app.route("/debug/accounts")
def debug_all_accounts():
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    url = "https://www.zohoapis.com/crm/v2/Accounts"
    params = {
        "page": 1,
        "per_page": 200  # Max allowed by Zoho
    }

    response = requests.get(url, headers=headers, params=params)
    print("🔍 Accounts Fetch URL:", response.url)
    return response.json()

# ---------------- Run Server ----------------
if __name__ == "__main__":
    app.run(port=8000)