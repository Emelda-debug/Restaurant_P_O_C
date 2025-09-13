import os
import re
import schedule
import time
import threading
import logging
from flask import Flask, request, session, jsonify, json, make_response
import requests
from flask_session import Session
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
#import spacy
import traceback
from base64 import b64decode, b64encode
from flask import Flask, request, jsonify, Response
from base64 import b64decode, b64encode
from cryptography.hazmat.primitives.asymmetric.padding import OAEP, MGF1
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes
from function_schemas import trigger_whatsapp_flow_schema, function_implementations
from db import get_db_connection, save_session_to_db
from whatsapp_utils import get_flow_available_menu, trigger_whatsapp_flow, send_whatsapp_message, send_template_message
from openai_handling import query_openai_model, summarize_session



from helpers import check_inactivity
from reservations import save_reservation, process_reservation_flow, cancel_reservation
from orders import process_order_flow, save_order, cancel_order, validate_order
from rating import process_order_rating_flow, process_reservation_rating_flow
from customers import get_customer_name
from db import log_conversation
from menu import send_daily_menu
from config import bcrypt
from app import dash_blueprint


# Load environment variables from .env file
load_dotenv()

# Load the private key string from environment variables
with open("whatsapp_flow_private_key.pem", "r") as key_file:
    PRIVATE_KEY = key_file.read()



# Set up environment variables for Meta API
os.environ['META_PHONE_NUMBER_ID'] 
os.environ['META_ACCESS_TOKEN']


# Load the NLP model
#nlp = spacy.load("en_core_web_sm")




# Flask application
app = Flask(__name__)
bcrypt.init_app(app)
app.register_blueprint(dash_blueprint)

# Configure Flask-Session
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem for development
app.config['SESSION_PERMANENT'] = False  # Sessions will not expire unless explicitly cleared 
app.config['SESSION_USE_SIGNER'] = True
app.secret_key = 'ghnvdre5h4562' 
Session(app)


# Add the app-level 404 handler
@app.errorhandler(404)
def not_found_error(error):
    """
    Handle 404 errors with custom animated page.
    """
    from flask import render_template
    return render_template('404.html'), 404


@app.route('/end-session', methods=['POST'])
def end_session():
    try:
        from_number = request.values.get('From', '').strip()

        # Summarize session
        session_summary = summarize_session(session.get('conversation', []))

        # Save summary to database
        save_session_to_db(from_number, session_summary)

        # Clear session
        session.clear()

        return "Session ended and data saved."
    except Exception as e:
        logging.error(f"Error ending session: {e}")
        return "Error ending session."
  






@app.route('/clear-session', methods=['GET'])
def clear_session():
    """
    Clear the entire session.
    """
    try:
        session.clear()  # Clear all session variables
        return "Session has been cleared.", 200
    except Exception as e:
        logging.error(f"Error clearing session: {e}")
        return "Error clearing session.", 500




@app.route('/get_available_menu_items', methods=['POST'])
def get_available_menu_items():
    try:
        # Parse and decrypt the request
        body = request.get_json()
        decrypted_data = decrypt_request(
            body["encrypted_flow_data"],
            body["encrypted_aes_key"],
            body["initial_vector"]
        )

        sending_screen_name = decrypted_data['decryptedBody']['screen']
        version = decrypted_data["decryptedBody"]["version"]
        logging.info(decrypted_data)
        if sending_screen_name == '':
            screen = {
                "version": version,
                "screen": "RECOMMEND",
                "data": {
                    "menu_items": get_flow_available_menu()
                }
            }
        elif sending_screen_name == 'RECOMMEND':
            screen = {
                "version": version,
                "screen": "DELIVERY_DETAILS",
                "data": {
                    "screen_0_Order_Item_0": decrypted_data["decryptedBody"]["data"]["screen_0_Order_Item_0"],
                    "screen_0_Delivery_1": decrypted_data["decryptedBody"]["data"]["screen_0_Delivery_1"]
                }
            }

        else:
            try:
                delivery_location =decrypted_data["decryptedBody"]["data"]["screen_1_location"]
            except:
                delivery_location = ""
            try:
                delivery_time = decrypted_data["decryptedBody"]["data"]["screen_1_Time_2"]
            except:
                delivery_time = ""
            screen = {
                "version": version,
                "screen": "SUCCESS",
                "data": {
                    "extension_message_response": {
                        "params": {
                            "flow_token": "token",
                            "screen_1_Name_0": decrypted_data["decryptedBody"]["data"]["screen_1_Name_0"],
                            "screen_1_Location_1": delivery_location,
                            #"screen_1_Location_1": decrypted_data["decryptedBody"]["data"]["123 Harare"],
                            #"screen_1_Time_2": decrypted_data["decryptedBody"]["data"]["screen_1_Time_2"],
                            "screen_0_Order_Item_0": decrypted_data["decryptedBody"]["data"]["screen_0_Order_Item_0"],
                            "screen_0_Delivery_1": decrypted_data["decryptedBody"]["data"]["screen_0_Delivery_1"]
                        }
                    }
                }
            }

        logging.info(f"screen submitting flow{screen}")


        # Encrypt and return the response
        encrypted_response = encrypt_response(screen, decrypted_data['aesKeyBuffer'], decrypted_data['initialVectorBuffer'])
        return Response(encrypted_response, content_type='text/plain')

    except Exception as e:
        logging.error(f"Error: {e}")
        error_response = {
            "version": "3.0",
            "data": {
                "status": "active"
            }
        }
        encrypted_error_response = encrypt_response(error_response, decrypted_data.get('aesKeyBuffer', b''), decrypted_data.get('initialVectorBuffer', b''))
        return Response(encrypted_error_response, content_type='text/plain')




def decrypt_request(encrypted_flow_data_b64, encrypted_aes_key_b64, initial_vector_b64):
    """Decrypts the request data using RSA and AES-GCM."""
    
    flow_data = b64decode(encrypted_flow_data_b64)
    iv = b64decode(initial_vector_b64)
    encrypted_aes_key = b64decode(encrypted_aes_key_b64)

    private_key = load_pem_private_key(PRIVATE_KEY.encode('utf-8'), password=b'root')

    # Decrypt the AES encryption key using RSA-OAEP
    aes_key = private_key.decrypt(
        encrypted_aes_key,
        OAEP(
            mgf=MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    # Separate encrypted data and authentication tag
    encrypted_flow_data_body = flow_data[:-16]
    encrypted_flow_data_tag = flow_data[-16:]

    # AES-GCM decryption
    decryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(iv, encrypted_flow_data_tag)
    ).decryptor()

    decrypted_data_bytes = decryptor.update(encrypted_flow_data_body) + decryptor.finalize()
    decrypted_data = json.loads(decrypted_data_bytes.decode("utf-8"))

    return {
        "decryptedBody": decrypted_data,
        "aesKeyBuffer": aes_key,
        "initialVectorBuffer": iv
    }


def encrypt_response(response, aes_key, iv):
    """Encrypts the response data using AES-GCM."""
    
    flipped_iv = bytes([b ^ 0xFF for b in iv])

    encryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(flipped_iv)
    ).encryptor()

    encrypted_data = encryptor.update(json.dumps(response).encode("utf-8")) + encryptor.finalize()
    return b64encode(encrypted_data + encryptor.tag).decode("utf-8")







@app.route('/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    """
    Handles WhatsApp Webhook Verification (GET request) and Incoming Messages (POST request).
    """

    #def whatsapp_webhook():
    """
    Handle GET requests for webhook verification and POST requests for incoming messages.
    """
    
    if request.method == 'GET':
        verify_token = os.getenv('VERIFY_TOKEN')
        hub_mode = request.args.get('hub.mode')
        hub_token = request.args.get('hub.verify_token')
        hub_challenge = request.args.get('hub.challenge')

        logging.info(f"Received verification: mode={hub_mode}, token={hub_token}")

        if not all([hub_mode, hub_token, hub_challenge]):
            logging.error("Missing parameters in GET request")
            return "Bad Request", 400

        if hub_mode == 'subscribe' and hub_token == verify_token:
            logging.info("Webhook verified successfully")
            return hub_challenge, 200
        else:
            logging.error(f"Verification failed. Expected token={verify_token}, got {hub_token}")
            return "Forbidden", 403
        
    # ✅ WhatsApp Message Handling
    elif request.method == 'POST':
        meta_phone_number_id = os.getenv('META_PHONE_NUMBER_ID')  # Ensure the environment variable is set
        meta_access_token = os.getenv('META_ACCESS_TOKEN')  # Ensure the environment variable is set
        url = f"https://graph.facebook.com/v13.0/{meta_phone_number_id}/messages"

        try:
            data = request.json
            if not data:
                logging.warning("❌ No data received in request.")
                return jsonify({"error": "No data received"}), 400
            
            logging.info(f"📩 Incoming Webhook Data: {json.dumps(data, indent=2)}")

            entry = data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})

            # ✅ Handle WhatsApp Status Updates
            if 'statuses' in value:
                logging.info("📩 Received WhatsApp message status update. No action needed.")
                return jsonify({"message": "Status update received"}), 200

            # ✅ Check if there are messages
            if 'messages' not in value:
                logging.warning("❌ No messages found in webhook event.")
                return jsonify({"error": "No messages found"}), 400

            message = value['messages'][0]
            from_number = message['from']
            
            incoming_message = message.get('text', {}).get('body', '').strip().lower()


            logging.info(f"📥 Message from {from_number}: {incoming_message}")
            
             # ✅ Check for inactivity and update session summary if needed
            check_inactivity(from_number)
            
            # Handle Reservation Rating
            if "r rate" in incoming_message.lower():
                logging.info(f"📥 Received reservation rating message: {incoming_message}")

                match = re.search(r"r rate (\d+)", incoming_message, re.IGNORECASE)
                if match:
                    rating = int(match.group(1))
                    logging.info(f"✅ Extracted reservation rating: {rating}")

                    if 1 <= rating <= 5:
                        conn = get_db_connection()
                        if not conn:
                            logging.error("❌ Database connection failed.")
                            bot_reply = "Database connection failed. Please try again later."
                        else:
                            try:
                                cursor = conn.cursor()

                                # Check if the user is rating a completed reservation
                                cursor.execute('''
                                    SELECT id FROM reservations 
                                    WHERE contact_number = %s AND reservations_done = TRUE
                                    ORDER BY created_at DESC LIMIT 1
                                ''', (from_number,))
                                reservation = cursor.fetchone()
                                logging.info(f"🔍 Fetched reservation: {reservation}")

                                if reservation:
                                    # Update the rating for the reservation
                                    cursor.execute('UPDATE reservations SET rating = %s WHERE id = %s', (rating, reservation[0]))
                                    conn.commit()
                                    logging.info(f"✅ Successfully committed reservation {reservation[0]} with rating {rating}")

                                    bot_reply = "Thank you for rating your reservation experience! 🌟 We hope to see you again soon."
                                
                                else:
                                    logging.warning("⚠️ No completed reservations found for this user.")
                                    bot_reply = (
                                        "We couldn't find a completed reservation to rate. "
                                        "Please ensure your reservation is marked as 'completed' before rating."
                                    )

                            except psycopg2.Error as e:
                                bot_reply = "An error occurred while processing your rating. Please try again later."
                                logging.error(f"❌ Database error: {e}")

                            finally:
                                cursor.close()
                                conn.close()
                                logging.info("🔚 Database connection closed.")

                    else:
                        logging.warning(f"⚠️ Invalid reservation rating received: {rating}")
                        bot_reply = "Please provide a rating between 1 and 5. Example: 'r rate 5'."

                else:
                    logging.warning("⚠️ Invalid reservation message format received.")
                    bot_reply = "To rate your reservation experience, reply with 'r rate [1-5]'. Example: 'r rate 5'."

                send_whatsapp_message(from_number, bot_reply)
                return "Message processed.", 200  # 




            # Handle Order Rating
            elif "rate" in incoming_message.lower():
                logging.info(f"📥 Received rating message: {incoming_message}")

                match = re.search(r"rate (\d+)", incoming_message, re.IGNORECASE)
                if match:
                    rating = int(match.group(1))
                    logging.info(f"✅ Extracted rating: {rating}")

                    if 1 <= rating <= 5:
                        conn = get_db_connection()
                        if not conn:
                            logging.error("❌ Database connection failed.")
                            bot_reply = "Database connection failed. Please try again later."
                        else:
                            try:
                                cursor = conn.cursor()

                                # Check if the user is rating a completed order
                                cursor.execute('''
                                    SELECT id FROM orders 
                                    WHERE contact_number = %s AND status = 'done' 
                                    ORDER BY created_at DESC LIMIT 1
                                ''', (from_number,))
                                order = cursor.fetchone()
                                logging.info(f"🔍 Fetched order: {order}")

                                if order:
                                    # Update the rating for the order
                                    cursor.execute('UPDATE orders SET rating = %s WHERE id = %s', (rating, order[0]))
                                    conn.commit()
                                    logging.info(f"✅ Successfully committed order {order[0]} with rating {rating}")

                                    bot_reply = "Thank you for rating your order experience! 🌟 We hope to see you again soon."
                                
                                else:
                                    logging.warning("⚠️ No completed orders found for this user.")
                                    bot_reply = (
                                        "We couldn't find a completed order to rate. "
                                        "Please ensure your order is marked as 'completed' before rating."
                                    )

                            except psycopg2.Error as e:
                                bot_reply = "An error occurred while processing your rating. Please try again later."
                                logging.error(f"❌ Database error: {e}")

                            finally:
                                cursor.close()
                                conn.close()
                                logging.info("🔚 Database connection closed.")

                    else:
                        logging.warning(f"⚠️ Invalid rating received: {rating}")
                        bot_reply = "Please provide a rating between 1 and 5. Example: 'Rate 5'."

                else:
                    logging.warning("⚠️ Invalid message format received.")
                    bot_reply = "To rate your experience, reply with 'Rate [1-5]'. Example: 'Rate 5'."

                send_whatsapp_message(from_number, bot_reply)
                return "Message processed.", 200
            

            # ⭐ Handling Table Booking
            elif "book table" in incoming_message:
                instruction_message = (
                    "📢 *Booking Instructions*\n"
                    "Please copy the template message below, paste it  and replace placeholder values with your details:"
                )
                send_whatsapp_message(from_number, instruction_message)

                # ✅ Second message: Booking form template
                template_message = (
                    "Reservation Name: Jane Doe\n"
                    "Date for Booking: 25 June\n"
                    "Time for Booking: 2 PM\n"
                    "Number of People: 4\n"
                    "Table Number: 1"
                )
                send_whatsapp_message(from_number, template_message)
                return "Message processed.", 200

            # ⭐ Handling Filled Booking Form
            elif "reservation name:" in incoming_message.lower():
                match = re.search(
                    r"Reservation Name:\s*(.+)\s*Date for Booking:\s*([0-9]{1,2} [A-Za-z]+)\s*Time for Booking:\s*([0-9]{1,2} [APap][Mm])\s*Number of People:\s*(\d+)\s*Table Number:\s*(\d+)",
                    incoming_message,
                    re.IGNORECASE
                )

                if match:
                    # Extract reservation details
                    name = match.group(1).strip()
                    reservation_date = match.group(2).strip()
                    reservation_time = match.group(3).strip()
                    number_of_people = int(match.group(4))
                    table_number = int(match.group(5))

                    # ✅ Save the reservation
                    bot_reply = save_reservation(name, from_number, reservation_date, reservation_time, number_of_people, table_number)

                    # ✅ Log response and send the reply to the user
                    logging.info(f"📌 Booking Response: {bot_reply}")
                    send_whatsapp_message(from_number, bot_reply)
                    return "Message processed.", 200
                else:
                    # ✅ If format is incorrect, ask user to follow template
                    bot_reply = (
                        "⚠️ Please provide correct details in the format:\n\n"
                        "**Reservation Name:** [Your Name]\n"
                        "**Date for Booking:** [DD Month]\n"
                        "**Time for Booking:** [HH AM/PM]\n"
                        "**Number of People:** [X]\n"
                        "**Table Number:** [Y]\n\n"
                        "Example:\n"
                        "Reservation Name: Emelda\n"
                        "Date for Booking: 25 June\n"
                        "Time for Booking: 2 PM\n"
                        "Number of People: 4\n"
                        "Table Number: 1"
                    )
                    send_whatsapp_message(from_number, bot_reply)
                    return "Message processed.", 200
            
            elif "reserve table" in incoming_message.lower():
                bot_reply = "🍽️ Let's book your table! Click below to start your reservation."
                flow_cta = "Start Booking"
                flow_name = "reservation"  

                # ✅ Trigger WhatsApp Flow for Reservation
                flow_response = trigger_whatsapp_flow(from_number, bot_reply, flow_cta, flow_name)

                logging.debug(f"🔍 Flow Trigger Debug - User: {from_number}, Response: {flow_response}")
                return jsonify({"message": "Reservation flow triggered"}), 200

                
            elif message.get('type') == "interactive":
                interactive_data = message.get('interactive', {})

                # ✅ Handle Flow Submission (nfm_reply)
                if interactive_data.get('type') == "nfm_reply":
                    
                    flow_response = interactive_data.get('nfm_reply', {}).get('response_json')

                    if flow_response:
                        response_data = json.loads(flow_response)  # Convert string to dictionary

                        # ✅ Dynamically Determine Flow Name Instead of Expecting Flow ID
                        flow_name = None
                        if "reservation_time" in response_data and "reservation_date" in response_data:
                            flow_name = "reservation"
                        elif any("Order_experience" in key for key in response_data.keys()):
                            flow_name = "order_rating"
                        elif any("Dining_Experience" in key for key in response_data.keys()):
                            flow_name = "reservation_rating"
                        if any("Order_Item" in key for key in response_data.keys()):
                            flow_name = "order_flow"


                        if not flow_name:
                            logging.warning("⚠️ Unable to determine Flow Name from response JSON.")
                            return jsonify({"error": "Flow Name missing or unrecognized"}), 400

                        # ✅ Correctly Process the Response Based on Flow Name
                        if flow_name == "reservation":
                            logging.info(f"✅ Detected Reservation Flow - Processing Reservation")
                            return process_reservation_flow(response_data, message)
                        elif flow_name == "order_rating":
                            logging.info(f"✅ Detected Order Rating Flow - Processing Order Rating")
                            return process_order_rating_flow(response_data, message)
                        elif flow_name == "reservation_rating":
                            logging.info(f"✅ Detected Reservation Rating Flow - Processing Reservation Rating")
                            return process_reservation_rating_flow(response_data, message)
                        elif flow_name == "order_flow":
                            logging.info(f"✅ Detected Order Flow - Processing Order")
                            return process_order_flow(response_data, message)

                                    # 🚨 If Flow Name is Unrecognized
                        logging.warning(f"⚠️ Unrecognized Flow Name: {flow_name}")
                        return jsonify({"error": "Unknown flow name"}), 400

                    else:
                        logging.warning("⚠️ Flow response JSON is missing.")
                        return jsonify({"error": "Flow response JSON missing"}), 400

                    return jsonify({"message": "Message processed"}), 200
            
               
                # if interactive_data.get('type') == "button_reply":
                #     logging.debug(f"🔘 Button reply received: {interactive_data}")  # Debug log
                    
                #     # Call your existing handle_button_reply function
                #     result = handle_button_reply(interactive_data, from_number)
                #     logging.info(f"📄 Button handler result: {result}")  # Debug log

                #     return jsonify(result), 200

            
            # ⭐ Handling Order Cancellation
            elif "cancel order" in incoming_message:
                match = re.search(r"cancel order for (.+)", incoming_message, re.IGNORECASE)
                if match:
                    order_details = match.group(1).strip()
                    bot_reply = cancel_order(from_number, order_details)
                else:
                    bot_reply = "Oh no 🥺, I'm sorry you want to cancel your order. To cancel order made under your number, type: 'Cancel order for [Order Details]' e.g. cancel order for cheese."

            # ⭐ Handling Reservation Cancellation
            elif "cancel reservation" in incoming_message:
                match = re.search(r"cancel reservation for table (\d+)", incoming_message, re.IGNORECASE)
                if match:
                    table_number = int(match.group(1))
                    bot_reply = cancel_reservation(from_number, table_number)
                else:
                    bot_reply = " Oh no 🥺, I'm sorry you want to cancel your reservation. I hope everything is okay."
                    "Please use the format to cancel reservations made under your number: 'Cancel reservation for table [Table Number]'."
                        
            elif incoming_message.lower() in ["clear context", "start over", "reset chat"]:
                session.clear()
                logging.info(f"🔄 Context cleared for {from_number}.")
                
                bot_reply = "Context has been cleared. Let's start fresh! How can I assist you?"
                send_whatsapp_message(from_number, bot_reply)
                return "Message processed.", 200
            
            elif "place order" in incoming_message.lower():
                bot_reply = "🛒 Let's place your order! Click below to start the process."
                flow_cta = "Start Order"
                flow_name = "order_flow"  # ✅ Use correct flow name from FLOW_IDS

                # ✅ Trigger WhatsApp Flow for Order Placement
                flow_response = trigger_whatsapp_flow(from_number, bot_reply, flow_cta, flow_name)

                logging.debug(f"🔍 Flow Trigger Debug - User: {from_number}, Response: {flow_response}")
                return jsonify({"message": "Order flow triggered"}), 200

            

            # ⭐ Handling Order Request (Sending Order Template)
            elif "make order" in incoming_message.lower():
                bot_reply=(
                    "🚚 *Would you like delivery for your order?*\n"
                    "👉 type *1y* - for Yes, I want delivery.\n"
                    "👉 type *2n* - for No, I will pick up."
                )
                send_whatsapp_message(from_number, bot_reply)
                return "Message processed.", 200
            
             # ⭐ Handling User Response for Delivery Choice
            elif incoming_message.strip().lower() == "1y":
                # ✅ Send template for delivery orders
                instruction_message = (
                    "🛒 *Order Instructions*\n"
                    "Since you've chosen *Delivery*, please copy the Order Form template message below and replace the placeholder details with your details."
                )
                send_whatsapp_message(from_number, instruction_message)

                template_message = (
                    " Order Form:\n"
                    "Order: BBQ Ribs, Mojito\n"
                    "Delivery: Yes\n"
                    "Name: Emelda\n"
                    "Location: 123 Main St\n"
                    "Time: 8 PM"
                )
                send_whatsapp_message(from_number, template_message)
                return "Message processed.", 200
            
            elif incoming_message.strip().lower() == "2n":
            
                instruction_message = (
                    "🛒 *Order Instructions*\n"
                    "Since you've chosen *No Delivery*, please copy the Order Form template below and replace the order details with the details of what you want to order."
                )
                send_whatsapp_message(from_number, instruction_message)

                template_message = (
                    " Order Form:\n"
                    "Order: BBQ Ribs, Mojito\n"
                    "Delivery: No\n"
                )
                send_whatsapp_message(from_number, template_message)
                return "Message processed.", 200

           # ⭐ Handling Order Placement After User Fills Template
            elif "order form:" in incoming_message.lower():
                match = re.search(
                    r"Order:\s*(.+?)\s*Delivery:\s*(yes|no)"
                    r"(?:\s*Name:\s*(.+?)\s*Location:\s*(.+?)\s*Time:\s*(.+))?",
                    incoming_message, re.IGNORECASE | re.DOTALL
                )

                if match:
                    # ✅ Extract details from user input
                    order_details = match.group(1).strip()
                    delivery_status = match.group(2).strip().lower()
                    delivery_name = match.group(3).strip() if match.group(3) else None
                    delivery_location = match.group(4).strip() if match.group(4) else None
                    delivery_time = match.group(5).strip() if match.group(5) else None

                    logging.info(f"🛒 Processing Order: {order_details}, Delivery: {delivery_status}, Name: {delivery_name}, Location: {delivery_location}, Time: {delivery_time}")

                    # ✅ Validate the order
                    try:
                        available_items, ordered_items = validate_order(order_details)
                    except Exception as e:
                        logging.error(f"❌ Error validating order: {e}")
                        bot_reply = "There was an issue validating your order. Please try again."
                        send_whatsapp_message(from_number, bot_reply)
                        return "Message processed.", 200

                    # ✅ Check if any ordered items are unavailable
                    unavailable_items = [item for item in ordered_items if item not in available_items]

                    if unavailable_items:
                        # ❌ Inform the user about unavailable items and suggest alternatives
                        conn = get_db_connection()
                        if not conn:
                            bot_reply = "Database connection failed. Please try again later."
                        else:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("SELECT item_name FROM menu WHERE available = TRUE")
                                menu_items = [row[0] for row in cursor.fetchall()]
                                
                                logging.info(f"❌ Unavailable Items: {unavailable_items}")
                                bot_reply = (
                                    f"❌ The following items are not available: {', '.join(unavailable_items)}.\n"
                                    "Here’s what we currently have on our menu:\n"
                                    f"{', '.join(menu_items)}\n Please resend your order form with the corrected menu item"
                                )
                            except psycopg2.Error as e:
                                logging.error(f"Database error: {e}")
                                bot_reply = "An error occurred while checking item availability. Please try again later."
                            finally:
                                cursor.close()
                                conn.close()

                    else:
                        # ✅ Save the order based on delivery status
                        if delivery_status == "no":
                            save_response = save_order(
                                contact_number=from_number,
                                order_details=", ".join(available_items),
                                delivery="No"
                            )
                            bot_reply = f"✅ Your order for {', '.join(available_items)} has been placed successfully. No delivery required, can't wait to see you when you come collect it."

                        elif delivery_status == "yes":
                            if delivery_name and delivery_location and delivery_time:
                                save_response = save_order(
                                    contact_number=from_number,
                                    order_details=", ".join(available_items),
                                    delivery="Yes",
                                    delivery_name=delivery_name,
                                    delivery_location=delivery_location,
                                    delivery_time=delivery_time
                                )
                                bot_reply = f"🚚 Order Confirmed! Your {', '.join(available_items)} will be delivered to {delivery_location} at {delivery_time}. Thank you for choosing Star!"
                            else:
                                bot_reply = "❌ Missing delivery details. Please provide Name, Location, and Time."

                else:
                    bot_reply = (
                        "❌ Invalid format. Please use: \n"
                       "The order form specified"
                    )

                # ✅ Send the final bot reply
                send_whatsapp_message(from_number, bot_reply)
                return "Message processed.", 200

              

                    # ⭐ Handling AI Responses
            else:
                user_history = summarize_session(from_number, [{"role": "user", "content": incoming_message}])
                if isinstance(user_history, list):  # Ensure user_history is a list before processing
                    formatted_history = "\n".join(
                        f"{msg['role']}: {msg['content']}" for msg in user_history if isinstance(msg, dict)
                    )
                else:
                    logging.error(f"❌ Unexpected type for user_history: {type(user_history)}")
                    formatted_history = user_history  

                session_summary = user_history if user_history else "No previous context."
                                

                # Detect if the message is a greeting or farewell
                if any(greeting in incoming_message.lower() for greeting in ["hello", "hi", "good morning","hey", "howdy", "good evening", "greetings"]):
                    # Append name to greeting
                    bot_reply = f"Hello {get_customer_name(from_number)}! " + query_openai_model(
                        incoming_message, session_summary, formatted_history, from_number
                    )
                elif any(farewell in incoming_message.lower() for farewell in ["bye", "goodbye", "see you", "take care"]):
                    # Append name to farewell
                    bot_reply = query_openai_model(
                        incoming_message, session_summary, formatted_history, from_number
                    ) + f" Goodbye {get_customer_name(from_number)}!"
                else:
                 bot_reply = query_openai_model(incoming_message, session_summary, formatted_history, from_number)

                # Log conversation only if bot_reply is meaningful
                if bot_reply and "✅ Function executed" not in bot_reply:
                    log_conversation(from_number, incoming_message, bot_reply, "processed")
                    send_whatsapp_message(from_number, bot_reply)
                else:
                    log_conversation(from_number, incoming_message, "[Function Triggered]", "processed")

                return "Message processed.", 200


            # ✅ Send response via WhatsApp Meta API
            headers = {
                "Authorization": f"Bearer {meta_access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": from_number,
                "type": "text",
                "text": {"body": bot_reply}
            }
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                logging.info(f"✅ Message Sent Successfully to {from_number}")
            else:
                logging.error(f"❌ Error Sending Message: {response.text}")

            return "Message processed.", 200
        
        except Exception as e:
            logging.error(f"❌ Error Processing Webhook: {e}")
            logging.error(traceback.format_exc())


# @app.route('/webhook', methods=['GET', 'POST'])
# def whatsapp_webhook():
#     """
#     Handles WhatsApp Webhook Verification (GET request) and Incoming Messages (POST request).
#     """
#     logging.info("🚀 WEBHOOK ENDPOINT HIT!")
#     logging.info(f"📥 Request Method: {request.method}")
#     logging.info(f"📥 Request Headers: {dict(request.headers)}")
    
#     if request.method == 'GET':
#         verify_token = os.getenv('VERIFY_TOKEN')
#         hub_mode = request.args.get('hub.mode')
#         hub_token = request.args.get('hub.verify_token')
#         hub_challenge = request.args.get('hub.challenge')

#         logging.info(f"Received verification: mode={hub_mode}, token={hub_token}")

#         if not all([hub_mode, hub_token, hub_challenge]):
#             logging.error("Missing parameters in GET request")
#             return "Bad Request", 400

#         if hub_mode == 'subscribe' and hub_token == verify_token:
#             logging.info("Webhook verified successfully")
#             return hub_challenge, 200
#         else:
#             logging.error(f"Verification failed. Expected token={verify_token}, got {hub_token}")
#             return "Forbidden", 403
        
#     # ✅ WhatsApp Message Handling
#     elif request.method == 'POST':
#         logging.info("📋 Processing POST request for message handling")
#         meta_phone_number_id = os.getenv('META_PHONE_NUMBER_ID')
#         meta_access_token = os.getenv('META_ACCESS_TOKEN')
#         url = f"https://graph.facebook.com/v13.0/{meta_phone_number_id}/messages"

#         try:
#             data = request.json
#             if not data:
#                 logging.warning("❌ No data received in request.")
#                 return jsonify({"error": "No data received"}), 400
            
#             logging.info(f"📩 Incoming Webhook Data: {json.dumps(data, indent=2)}")

#             entry = data.get('entry', [{}])[0]
#             changes = entry.get('changes', [{}])[0]
#             value = changes.get('value', {})

#             # ✅ Handle WhatsApp Status Updates
#             if 'statuses' in value:
#                 logging.info("📩 Received WhatsApp message status update. No action needed.")
#                 return jsonify({"message": "Status update received"}), 200

#             # ✅ Check if there are messages
#             if 'messages' not in value:
#                 logging.warning("❌ No messages found in webhook event.")
#                 return jsonify({"error": "No messages found"}), 400

#             message = value['messages'][0]
#             from_number = message['from']
#             message_type = message.get('type', '')
            
#             logging.info(f"📥 Message type: {message_type} from {from_number}")
            
#             # ✅ Check for inactivity and update session summary if needed
#             check_inactivity(from_number)
            
#             # ✅ Handle Interactive Messages (Buttons and Flows)
#             if message_type == "interactive":
#                 logging.info("🎯 INTERACTIVE MESSAGE DETECTED!")
#                 logging.info(f"🔘 Interactive message received: {json.dumps(message, indent=2)}")
                
#                 interactive_data = message.get('interactive', {})
#                 interactive_type = interactive_data.get('type', '')
                
#                 logging.info(f"🔘 Interactive type: {interactive_type}")
#                 logging.info(f"🔘 Interactive data: {json.dumps(interactive_data, indent=2)}")


#                 # ✅ Handle Button Reply
#                 if interactive_type == "button_reply":
#                     logging.info(f"🔘 Button reply received: {interactive_data}")
                    
#                     try:
#                         # Call your existing handle_button_reply function
#                         result = handle_button_reply(interactive_data, from_number)
#                         logging.info(f"📄 Button handler result: {result}")
                        
#                         return jsonify(result), 200
#                     except Exception as e:
#                         logging.error(f"❌ Error in handle_button_reply: {e}")
#                         logging.error(traceback.format_exc())
#                         return jsonify({"error": "Button handling failed"}), 500
                    

#                 # ✅ Handle Flow Submission (nfm_reply)
#                 elif interactive_type == "nfm_reply":
#                     logging.info(f"📱 Flow submission received")
                    
#                     flow_response = interactive_data.get('nfm_reply', {}).get('response_json')

#                     if flow_response:
#                         response_data = json.loads(flow_response)
#                         logging.info(f"📱 Flow response data: {response_data}")

#                         # ✅ Dynamically Determine Flow Name
#                         flow_name = None
#                         if "reservation_time" in response_data and "reservation_date" in response_data:
#                             flow_name = "reservation"
#                         elif any("Order_experience" in key for key in response_data.keys()):
#                             flow_name = "order_rating"
#                         elif any("Dining_Experience" in key for key in response_data.keys()):
#                             flow_name = "reservation_rating"
#                         elif any("Order_Item" in key for key in response_data.keys()):
#                             flow_name = "order_flow"

#                         if not flow_name:
#                             logging.warning("⚠️ Unable to determine Flow Name from response JSON.")
#                             return jsonify({"error": "Flow Name missing or unrecognized"}), 400

#                         # ✅ Process the Response Based on Flow Name
#                         if flow_name == "reservation":
#                             logging.info(f"✅ Processing Reservation Flow")
#                             return process_reservation_flow(response_data, message)
#                         elif flow_name == "order_rating":
#                             logging.info(f"✅ Processing Order Rating Flow")
#                             return process_order_rating_flow(response_data, message)
#                         elif flow_name == "reservation_rating":
#                             logging.info(f"✅ Processing Reservation Rating Flow")
#                             return process_reservation_rating_flow(response_data, message)
#                         elif flow_name == "order_flow":
#                             logging.info(f"✅ Processing Order Flow")
#                             return process_order_flow(response_data, message)

#                         # 🚨 If Flow Name is Unrecognized
#                         logging.warning(f"⚠️ Unrecognized Flow Name: {flow_name}")
#                         return jsonify({"error": "Unknown flow name"}), 400

#                     else:
#                         logging.warning("⚠️ Flow response JSON is missing.")
#                         return jsonify({"error": "Flow response JSON missing"}), 400

#                 # ✅ Handle other interactive types
#                 else:
#                     logging.warning(f"⚠️ Unhandled interactive type: {interactive_type}")
#                     return jsonify({"message": "Interactive message received but not handled"}), 200

#             # ✅ Handle Text Messages
#             elif message_type == "text":
#                 incoming_message = message.get('text', {}).get('body', '').strip().lower()
#                 logging.info(f"📥 Text message from {from_number}: {incoming_message}")
                
#                 # Handle Reservation Rating
#                 if "r rate" in incoming_message:
#                     logging.info(f"📥 Received reservation rating message: {incoming_message}")

#                     match = re.search(r"r rate (\d+)", incoming_message, re.IGNORECASE)
#                     if match:
#                         rating = int(match.group(1))
#                         logging.info(f"✅ Extracted reservation rating: {rating}")

#                         if 1 <= rating <= 5:
#                             conn = get_db_connection()
#                             if not conn:
#                                 logging.error("❌ Database connection failed.")
#                                 bot_reply = "Database connection failed. Please try again later."
#                             else:
#                                 try:
#                                     cursor = conn.cursor()

#                                     # Check if the user is rating a completed reservation
#                                     cursor.execute('''
#                                         SELECT id FROM reservations 
#                                         WHERE contact_number = %s AND reservations_done = TRUE
#                                         ORDER BY created_at DESC LIMIT 1
#                                     ''', (from_number,))
#                                     reservation = cursor.fetchone()
#                                     logging.info(f"🔍 Fetched reservation: {reservation}")

#                                     if reservation:
#                                         # Update the rating for the reservation
#                                         cursor.execute('UPDATE reservations SET rating = %s WHERE id = %s', (rating, reservation[0]))
#                                         conn.commit()
#                                         logging.info(f"✅ Successfully committed reservation {reservation[0]} with rating {rating}")

#                                         bot_reply = "Thank you for rating your reservation experience! 🌟 We hope to see you again soon."
                                    
#                                     else:
#                                         logging.warning("⚠️ No completed reservations found for this user.")
#                                         bot_reply = (
#                                             "We couldn't find a completed reservation to rate. "
#                                             "Please ensure your reservation is marked as 'completed' before rating."
#                                         )

#                                 except psycopg2.Error as e:
#                                     bot_reply = "An error occurred while processing your rating. Please try again later."
#                                     logging.error(f"❌ Database error: {e}")

#                                 finally:
#                                     cursor.close()
#                                     conn.close()
#                                     logging.info("🔚 Database connection closed.")

#                         else:
#                             logging.warning(f"⚠️ Invalid reservation rating received: {rating}")
#                             bot_reply = "Please provide a rating between 1 and 5. Example: 'r rate 5'."

#                     else:
#                         logging.warning("⚠️ Invalid reservation message format received.")
#                         bot_reply = "To rate your reservation experience, reply with 'r rate [1-5]'. Example: 'r rate 5'."

#                     send_whatsapp_message(from_number, bot_reply)
#                     return "Message processed.", 200

#                 # Handle Order Rating
#                 elif "rate" in incoming_message:
#                     logging.info(f"📥 Received rating message: {incoming_message}")

#                     match = re.search(r"rate (\d+)", incoming_message, re.IGNORECASE)
#                     if match:
#                         rating = int(match.group(1))
#                         logging.info(f"✅ Extracted rating: {rating}")

#                         if 1 <= rating <= 5:
#                             conn = get_db_connection()
#                             if not conn:
#                                 logging.error("❌ Database connection failed.")
#                                 bot_reply = "Database connection failed. Please try again later."
#                             else:
#                                 try:
#                                     cursor = conn.cursor()

#                                     # Check if the user is rating a completed order
#                                     cursor.execute('''
#                                         SELECT id FROM orders 
#                                         WHERE contact_number = %s AND status = 'done' 
#                                         ORDER BY created_at DESC LIMIT 1
#                                     ''', (from_number,))
#                                     order = cursor.fetchone()
#                                     logging.info(f"🔍 Fetched order: {order}")

#                                     if order:
#                                         # Update the rating for the order
#                                         cursor.execute('UPDATE orders SET rating = %s WHERE id = %s', (rating, order[0]))
#                                         conn.commit()
#                                         logging.info(f"✅ Successfully committed order {order[0]} with rating {rating}")

#                                         bot_reply = "Thank you for rating your order experience! 🌟 We hope to see you again soon."
                                    
#                                     else:
#                                         logging.warning("⚠️ No completed orders found for this user.")
#                                         bot_reply = (
#                                             "We couldn't find a completed order to rate. "
#                                             "Please ensure your order is marked as 'completed' before rating."
#                                         )

#                                 except psycopg2.Error as e:
#                                     bot_reply = "An error occurred while processing your rating. Please try again later."
#                                     logging.error(f"❌ Database error: {e}")

#                                 finally:
#                                     cursor.close()
#                                     conn.close()
#                                     logging.info("🔚 Database connection closed.")

#                         else:
#                             logging.warning(f"⚠️ Invalid rating received: {rating}")
#                             bot_reply = "Please provide a rating between 1 and 5. Example: 'Rate 5'."

#                     else:
#                         logging.warning("⚠️ Invalid message format received.")
#                         bot_reply = "To rate your experience, reply with 'Rate [1-5]'. Example: 'Rate 5'."

#                     send_whatsapp_message(from_number, bot_reply)
#                     return "Message processed.", 200

                

#                 # ⭐ Handling Filled Booking Form
#                 elif "reservation name:" in incoming_message:
#                     match = re.search(
#                         r"Reservation Name:\s*(.+)\s*Date for Booking:\s*([0-9]{1,2} [A-Za-z]+)\s*Time for Booking:\s*([0-9]{1,2} [APap][Mm])\s*Number of People:\s*(\d+)\s*Table Number:\s*(\d+)",
#                         incoming_message,
#                         re.IGNORECASE
#                     )

#                     if match:
#                         # Extract reservation details
#                         name = match.group(1).strip()
#                         reservation_date = match.group(2).strip()
#                         reservation_time = match.group(3).strip()
#                         number_of_people = int(match.group(4))
#                         table_number = int(match.group(5))

#                         # ✅ Save the reservation
#                         bot_reply = save_reservation(name, from_number, reservation_date, reservation_time, number_of_people, table_number)

#                         # ✅ Log response and send the reply to the user
#                         logging.info(f"📌 Booking Response: {bot_reply}")
#                         send_whatsapp_message(from_number, bot_reply)
#                         return "Message processed.", 200
#                     else:
#                         # ✅ If format is incorrect, ask user to follow template
#                         bot_reply = (
#                             "⚠️ Please provide correct details in the format:\n\n"
#                             "**Reservation Name:** [Your Name]\n"
#                             "**Date for Booking:** [DD Month]\n"
#                             "**Time for Booking:** [HH AM/PM]\n"
#                             "**Number of People:** [X]\n"
#                             "**Table Number:** [Y]\n\n"
#                             "Example:\n"
#                             "Reservation Name: Emelda\n"
#                             "Date for Booking: 25 June\n"
#                             "Time for Booking: 2 PM\n"
#                             "Number of People: 4\n"
#                             "Table Number: 1"
#                         )
#                         send_whatsapp_message(from_number, bot_reply)
#                         return "Message processed.", 200
            

#                 # ⭐ Handling AI Responses
#                 else:
#                     user_history = summarize_session(from_number, [{"role": "user", "content": incoming_message}])
#                     if isinstance(user_history, list):
#                         formatted_history = "\n".join(
#                             f"{msg['role']}: {msg['content']}" for msg in user_history if isinstance(msg, dict)
#                         )
#                     else:
#                         logging.error(f"❌ Unexpected type for user_history: {type(user_history)}")
#                         formatted_history = user_history  

#                     session_summary = user_history if user_history else "No previous context."
                                    

#                     # Detect if the message is a greeting or farewell
#                     if any(greeting in incoming_message for greeting in ["hello", "hi", "good morning","hey", "howdy", "good evening", "greetings"]):
#                         # Append name to greeting
#                         bot_reply = f"Hello {get_customer_name(from_number)}! " + query_openai_model(
#                             incoming_message, session_summary, formatted_history, from_number
#                         )
#                     elif any(farewell in incoming_message for farewell in ["bye", "goodbye", "see you", "take care"]):
#                         # Append name to farewell
#                         bot_reply = query_openai_model(
#                             incoming_message, session_summary, formatted_history, from_number
#                         ) + f" Goodbye {get_customer_name(from_number)}!"
#                     else:
#                         bot_reply = query_openai_model(incoming_message, session_summary, formatted_history, from_number)

#                     # Log conversation only if bot_reply is meaningful
#                     if bot_reply and "✅ Function executed" not in bot_reply:
#                         log_conversation(from_number, incoming_message, bot_reply, "processed")
#                         send_whatsapp_message(from_number, bot_reply)
#                         return "Message processed.", 200
#                     else:
#                         log_conversation(from_number, incoming_message, "[Function Triggered]", "processed")
#                         return "Message processed.", 200

#             # ✅ Handle Other Message Types
#             else:
#                 logging.warning(f"⚠️ Unhandled message type: {message_type}")
#                 return jsonify({"message": f"Unhandled message type: {message_type}"}), 200

#         except Exception as e:
#             logging.error(f"❌ Error Processing Webhook: {e}")
#             logging.error(traceback.format_exc())
#             return jsonify({"error": "Internal server error"}), 500


# def send_periodic_updates():
#     """Send periodic updates to the admin."""
#     conn = get_db_connection()
#     if not conn:
#         return

#     try:
#         cursor = conn.cursor()
#         cursor.execute('SELECT from_number, message, bot_reply FROM restaurant WHERE reported = 0')
#         restaurant = cursor.fetchall()

#         if restaurant:
#             update_message = "Hourly Update:\n\n"
#             for conv in restaurant:
#                 from_number, message, bot_reply = conv
#                 update_message += f"From: {from_number}\nMessage: {message}\nBot Reply: {bot_reply}\n\n"

#             send_whatsapp_message(ADMIN_NUMBER, update_message)

#             cursor.execute('UPDATE restaurant SET reported = 1 WHERE reported = 0')
#             conn.commit()

#     except psycopg2.Error as e:
#         logging.error(f"Database error: {e}")

#     finally:
#         cursor.close()
#         conn.close()

# schedule.every().hour.do(send_periodic_updates)

# Schedule the proactive messaging function
#schedule.every(2).minutes.do(send_intro_to_new_customers)

#Schedule Bulk Messaging 
schedule.every().day.at("09:00").do(send_daily_menu)
#schedule.every(1).minute.do(send_daily_menu)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)




if __name__ == '__main__':
    #init_db()
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=5000, debug=True)
