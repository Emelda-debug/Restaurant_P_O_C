from config import logging
import os
import requests
from db import get_db_connection
import psycopg2
from dotenv import load_dotenv
import time


load_dotenv()

FLOW_IDS = {
    "reservation": os.getenv("WHATSAPP_FLOW_RESERVATION"),
    "reservation_rating": os.getenv("WHATSAPP_FLOW_RESERVATION_RATING"),
    "order_rating": os.getenv("WHATSAPP_FLOW_ORDER_RATING"),
    "order_flow": os.getenv("WHATSAPP_FLOW_ORDER")
}




def trigger_whatsapp_flow(to_number, message, flow_cta, flow_name):
    """
    Sends a request to trigger a WhatsApp Flow with the correct structure.
    Uses logging for debugging.
    """
    PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID") 
    ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")  
    
    flow_id = FLOW_IDS.get(flow_name)

    # ✅ Log environment variables
    logging.debug(f"📢 Triggering WhatsApp Flow for {to_number}")
    logging.debug(f"🔍 PHONE_NUMBER_ID: {PHONE_NUMBER_ID}")
    logging.debug(f"🔍 FLOW_ID: {flow_id}")
    
    if not PHONE_NUMBER_ID or not ACCESS_TOKEN or not flow_id:
        logging.error(f"❌ Missing required variables! Flow Name: {flow_name}, Flow ID: {flow_id}")
        return "Error: Missing environment variables."

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {
                "text" : message
            },
            "action": {
                "name" : "flow",
                "parameters": {
                    "flow_id": flow_id,
                    "flow_cta": flow_cta,
                    "flow_token": 'rufaro_is_a_genius',
                    "flow_message_version": 3,
                    "mode": 'published',
                    "flow_action_payload": {
                        "screen": "RECOMMEND",
                        "data": {
                            "menu_items": get_flow_available_menu()
                        }
                    }
                }
            }
        }
    }
    

    # ✅ Log the payload before sending the request
    logging.debug(f"📤 Sending Flow Request: {payload}")

    response = requests.post(url, headers=headers, json=payload)

    # ✅ Log API response
    logging.debug(f"🔍 WhatsApp API Response ({response.status_code}): {response.text}")

    if response.status_code == 200:
        logging.info(f"✅ Flow triggered successfully for {to_number}")
        return "Flow triggered successfully."
    else:
        logging.error(f"❌ Error triggering flow for {to_number}: {response.text}")
        return f"Error triggering flow: {response.text}"



def get_flow_available_menu():
    """Retrieve the menu from the database."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT item_name, price FROM menu WHERE available = TRUE ORDER BY item_name')
        menu_items = cursor.fetchall()

        # Organize the menu into categories
        menu = []
        for menu_item in menu_items:
            logging.info(menu_item)
            item = {
                "id": menu_item[0],
                "title" : f"{menu_item[0]} - ${menu_item[1]:.2f}"
            }
            menu.append(item)

    except psycopg2.Error as e:
        logging.warning(f"Database error while retrieving menu: {e}")
        menu = []

    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed

    return menu



# Send WhatsApp message
def send_whatsapp_message(to, message=None, flow_id=None):
    """
    Sends a WhatsApp message.
    - If `flow_id` is provided, it sends a WhatsApp Flow.
    - Otherwise, it sends a normal text message.
    """
    PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")  # WhatsApp Business API Phone Number ID
    ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")  # Your API Access Token

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # ✅ Send WhatsApp Flow if `flow_id` is provided
    if flow_id:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "flow": {
                    "flow_message_version": "3",
                    "flow_id": flow_id  
                }
            }
        }
    # ✅ Send a normal text message if `flow_id` is NOT provided
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        print(f"✅ Message sent successfully to {to}")
    else:
        print(f"❌ Error sending message: {response.text}")





def send_template_message(to, template_name, template_variables, header_image_url=None):
    """
    Send a WhatsApp template message via the WhatsApp Cloud API with correctly formatted parameters.
    """

    PHONE_NUMBER_ID = os.getenv('META_PHONE_NUMBER_ID')
    ACCESS_TOKEN = os.getenv('META_ACCESS_TOKEN')

    if not PHONE_NUMBER_ID or not ACCESS_TOKEN:
        logging.error("❌ META_PHONE_NUMBER_ID or META_ACCESS_TOKEN is missing in .env file!")
        return

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # Default to a known working image URL if not provided
    if not header_image_url:
        header_image_url = "https://drive.google.com/uc?id=1epvMKHgTqnzD8DSYHuvaApg3HJSTk1Xt"

    # Extract customer name properly from dictionary
    customer_name = template_variables.get("customer_name", "Customer")

    logging.debug(f"📢 Preparing to send WhatsApp template message to {to}")
    logging.debug(f"🔹 Template Name: {template_name}")
    logging.debug(f"🔹 Language Code: en")
    logging.debug(f"🔹 Header Image URL: {header_image_url}")
    logging.debug(f"🔹 Customer Name for Body Text: {customer_name}")

    # Build the correctly formatted payload
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "HEADER",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {
                                "link": header_image_url
                            }
                        }
                    ]
                },
                {
                    "type": "BODY",
                    "parameters": [
                        {
                            "type": "text",
                            "text": customer_name,
                            "parameter_name": "customer_name"  # ✅ Named parameter fix
                        }
                    ]
                }
            ]
        }
    }

    # Log payload for debugging
    logging.debug(f"📤 Final Payload Sent: {payload}")

    # Define request URL
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    # Log the headers and URL before making the request
    logging.debug(f"🔗 API Request URL: {url}")
    logging.debug(f"📡 Headers: {headers}")

    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers)
        response_time = round(time.time() - start_time, 2)

        response_json = response.json()  # Capture JSON response

        # Log full response for debugging
        logging.debug(f"📡 Full API Response ({response_time}s): {response_json}")

        if response.status_code == 200:
            logging.info(f"✅ Template message sent successfully to {to}")
        else:
            logging.error(f"❌ Failed to send template message to {to}: {response_json}")
            logging.error(f"🚨 HTTP Status Code: {response.status_code}")

        return response_json

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Network error sending template message to {to}: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")


def send_whatsapp_image(to, image_source, caption=None):
    """
    Send a WhatsApp image message via the WhatsApp Cloud API.
    
    Args:
        to (str): Recipient's phone number (with country code, e.g., "1234567890")
        image_source (str): URL of the image OR local file path
        caption (str, optional): Optional caption text for the image
    
    Returns:
        dict: API response from WhatsApp
    """
    PHONE_NUMBER_ID = os.getenv('META_PHONE_NUMBER_ID')
    ACCESS_TOKEN = os.getenv('META_ACCESS_TOKEN')
    
    if not PHONE_NUMBER_ID or not ACCESS_TOKEN:
        logging.error("❌ META_PHONE_NUMBER_ID or META_ACCESS_TOKEN is missing in .env file!")
        return {"error": "Missing credentials"}
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Check if image_source is a local file path
    if os.path.isfile(image_source):
        # It's a local file - upload to WhatsApp media first
        try:
            media_id = upload_image_to_whatsapp(image_source, ACCESS_TOKEN, PHONE_NUMBER_ID)
            
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": {"id": media_id}  # Use media_id for uploaded files
            }
            if caption:
                payload["image"]["caption"] = caption
                
        except Exception as e:
            logging.error(f"❌ Failed to upload image: {e}")
            return {"error": f"Upload failed: {str(e)}"}
    else:
        # It's a URL - use link method
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"link": image_source}  # Use URL directly
        }
        if caption:
            payload["image"]["caption"] = caption
    
    # Define request URL
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    
    # Log the request details
    logging.debug(f"📢 Sending WhatsApp image to {to}")
    logging.debug(f"🖼️ Image URL: {image_source}")
    logging.debug(f"💬 Caption: {caption}")
    logging.debug(f"📤 Payload: {payload}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers)
        response_time = round(time.time() - start_time, 2)
        
        response_json = response.json()
        
        # Log full response for debugging
        logging.debug(f"📡 Full API Response ({response_time}s): {response_json}")
        
        if response.status_code == 200:
            logging.info(f"✅ Image sent successfully to {to}")
        else:
            logging.error(f"❌ Failed to send image to {to}: {response_json}")
            logging.error(f"🚨 HTTP Status Code: {response.status_code}")
        
        return response_json
        
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Network error sending image to {to}: {str(e)}")
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}"}
    
def upload_image_to_whatsapp(image_path, access_token, phone_number_id):
    """Upload image to WhatsApp media endpoint and return media_id"""
    upload_url = f"https://graph.facebook.com/v18.0/{phone_number_id}/media"
    
    # Determine the correct MIME type based on file extension
    if image_path.lower().endswith('.png'):
        mime_type = 'image/png'
    elif image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
        mime_type = 'image/jpeg'
    elif image_path.lower().endswith('.webp'):
        mime_type = 'image/webp'
    else:
        mime_type = 'image/png'  # Default fallback
    
    with open(image_path, 'rb') as image_file:
        files = {
            'file': (os.path.basename(image_path), image_file, mime_type),  # Include filename and MIME type
            'messaging_product': (None, 'whatsapp')
        }
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        response = requests.post(upload_url, files=files, headers=headers)
        
    if response.status_code == 200:
        return response.json()['id']
    else:
        raise Exception(f"Upload failed: {response.text}")

def send_whatsapp_interactive(phone_number, body_text, button_id, button_title):
    """
    Send a WhatsApp interactive button message.
    """
    PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")  # WhatsApp Business API Phone Number ID
    ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")  # Your API Access Token

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "Welcome!"
            },
            "body": {
                "text": body_text
            },
            "footer": {
                "text": "Tap a button below"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": button_id,
                            "title": button_title
                        }
                    }
                ]
            }
        }
    }

    # Log the payload
    logging.debug(f"📤 Sending Interactive Message: {payload}")

    response = requests.post(url, headers=headers, json=payload)

    # Log the response
    logging.debug(f"🔍 WhatsApp API Response ({response.status_code}): {response.text}")

    if response.status_code == 200:
        logging.info(f"✅ Interactive message sent successfully to {phone_number}")
        return "Interactive message sent successfully."
    else:
        logging.error(f"❌ Error sending interactive message to {phone_number}: {response.text}")
        return f"Error sending interactive message: {response.text}"



# def handle_button_reply(interactive_data, from_number):
#     from menu import send_menu_page
#     logging.info(f"🔘 Button reply function called for {from_number}")
#     logging.info(f"🔘 Interactive data: {interactive_data}")
#     if interactive_data.get('type') == "button_reply":
#         button_reply = interactive_data.get('button_reply', {})
#         button_id = button_reply.get('id', '')
        
#         if button_id.startswith("next_page_"):
#             # Extract the next page number
#             next_page = int(button_id.split("_")[-1])
            
#             # Get the last query from database
#             last_query = get_user_last_query(from_number)
            
#             if last_query:
#                 # Get items for this category again
#                 conn = get_db_connection()
#                 cursor = conn.cursor()
#                 try:
#                     cursor.execute("""
#                         SELECT item_name, price, image_url 
#                         FROM menu 
#                         WHERE LOWER(category) = %s
#                     """, (last_query.lower(),))
#                     items = cursor.fetchall()
                    
#                     if items:
#                         send_menu_page(items, from_number, last_query, next_page)
#                         return {"message": f"Sent page {next_page}"}
#                 finally:
#                     cursor.close()
#                     conn.close()
            
#             return {"message": "Could not find previous query"}
    
#     return {"message": "Message processed"}