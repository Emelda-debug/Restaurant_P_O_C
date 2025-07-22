import os
import re
import schedule
import time
import threading
import logging
from flask import Flask, request, session, jsonify, json, make_response
from openai import OpenAI
import requests
from flask_session import Session
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
import spacy
import traceback
from base64 import b64decode, b64encode
from flask import Flask, request, jsonify, Response
from base64 import b64decode, b64encode
from cryptography.hazmat.primitives.asymmetric.padding import OAEP, MGF1
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes



# Load environment variables from .env file
load_dotenv()

# Load the private key string from environment variables
with open("whatsapp_flow_private_key.pem", "r") as key_file:
    PRIVATE_KEY = key_file.read()



# Set up environment variables for Meta API
os.environ['META_PHONE_NUMBER_ID'] 
os.environ['META_ACCESS_TOKEN']
os.environ['OPENAI_API_KEY'] 

FLOW_IDS = {
    "reservation": os.getenv("WHATSAPP_FLOW_RESERVATION"),
    "reservation_rating": os.getenv("WHATSAPP_FLOW_RESERVATION_RATING"),
    "order_rating": os.getenv("WHATSAPP_FLOW_ORDER_RATING"),
    "order_flow": os.getenv("WHATSAPP_FLOW_ORDER"),
}



 #Initialize OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

# Load the NLP model
nlp = spacy.load("en_core_web_sm")

# Configure Logging
logging.basicConfig(
    filename="agent.log",  
    level=logging.DEBUG,  
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Flask application
app = Flask(__name__)

# Configure Flask-Session
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem for development
app.config['SESSION_PERMANENT'] = False  # Sessions will not expire unless explicitly cleared 
app.config['SESSION_USE_SIGNER'] = True
app.secret_key = 'ghnvdre5h4562' 
Session(app)



# Admin number to send periodic updates
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')

def init_db():
    """
    Initializes the PostgreSQL database by creating the necessary tables
    for conversation logging, reservations, and orders.
    """
    conn = get_db_connection()
    if conn is None:
        logging.error("Failed to establish database connection. Cannot initialize tables.")
        return

    try:
        cursor = conn.cursor()

        # Create restaurant table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restaurant (
                id SERIAL PRIMARY KEY,
                from_number TEXT NOT NULL,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bot_reply TEXT,
                status TEXT,
                reported INTEGER DEFAULT 0
            )
        ''')

        # Create reservations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                contact_number TEXT NOT NULL,
                reservation_time TIMESTAMP NOT NULL,
                number_of_people INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reservations_done INTEGER DEFAULT 0,
                rating INTEGER
            )
        ''')

        # Create orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                contact_number TEXT NOT NULL,
                order_details TEXT NOT NULL,
                delivery TEXT DEFAULT 'No',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivery_name TEXT,
                delivery_location TEXT, 
                delivery_time TEXT,
                status TEXT,
                rating INTEGER
            )
        ''')

        # Commit the changes
        conn.commit()
        logging.info("Database tables initialized successfully.")

    except psycopg2.Error as e:
        logging.error(f"Error while creating tables: {e}")
        conn.rollback()
    finally:
        # Close the cursor and connection
        cursor.close()
        conn.close()


def get_db_connection():
    """Creates and returns a PostgreSQL database connection."""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT')
            )
        return conn
    except psycopg2.Error as e:
        logging.error(f"Database connection error: {e}")
        return None



def get_user_preferences(contact_number):
    """
    Retrieve user preferences and memory from the database.
    """
    conn = get_db_connection()
    if not conn:
        return {}
    try:
            cursor = conn.cursor()
            cursor.execute('SELECT memory_key, value FROM user_memory WHERE contact_number = %s', (contact_number,))
            preferences = {row[0]: row[1] for row in cursor.fetchall()}
            return preferences
    except psycopg2.Error as e:
        logging.error(f"Database error while retrieving preferences: {e}")
        preferences = {}
    finally:
        cursor.close()
        conn.close()

    return preferences


import json

def summarize_session(contact_number, current_conversation=None):
    """
    Retrieve past session summaries, user preferences, and recent messages to provide full context.
    """
    try:
        logging.info(f"🔍 Summarizing session for {contact_number}...")
        conn = get_db_connection()
        if not conn:
            logging.error("❌ Database connection failed in summarize_session()")
            return "No conversation history available."

        cursor = conn.cursor()

        # 1️⃣ Retrieve stored session summary from user_memory
        cursor.execute('''
            SELECT value FROM user_memory WHERE contact_number = %s AND memory_key = 'session_summary'
        ''', (contact_number,))
        stored_summary = cursor.fetchone()
        stored_summary = stored_summary[0] if stored_summary else "No previous context available."
        logging.info(f"📝 Stored Summary Retrieved: {stored_summary}")

        # 2️⃣ Retrieve last 5–10 messages for immediate context (✅ Fixed table name)
        cursor.execute('''
            SELECT message, bot_reply FROM restaurant
            WHERE from_number = %s
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (contact_number,))
        recent_messages = cursor.fetchall()

        if not recent_messages:
            logging.warning(f"⚠️ No recent messages found for {contact_number}")

        # Format messages for OpenAI
        recent_history = "\n".join([f"User: {msg} | Bot: {resp}" for msg, resp in recent_messages])
        logging.info(f"📜 Recent Messages Retrieved: {recent_history}")

        # 3️⃣ Retrieve user preferences
        preferences = get_user_preferences(contact_number)
        preferences_summary = ", ".join([f"{key}: {value}" for key, value in preferences.items()]) if preferences else "No preferences stored."
        logging.info(f"🔧 User Preferences Retrieved: {preferences_summary}")

        # 4️⃣ Include ongoing messages if available
        if current_conversation and isinstance(current_conversation, list):
            ongoing_conversation = "\n".join(
                [f"User: {msg['content']}" if isinstance(msg, dict) and "content" in msg else "Invalid data" for msg in current_conversation]
            )
        else:
            ongoing_conversation = ""

        logging.info(f"💬 Ongoing Conversation: {ongoing_conversation}")

        # 5️⃣ Merge stored summary, user preferences, recent messages, and ongoing messages
        full_context = f"""
        **User Preferences:** 
        {preferences_summary}

        **Stored Summary:** 
        {stored_summary}

        **Recent Messages:** 
        {recent_history}

        **Ongoing Messages:** 
        {ongoing_conversation}
        """
        logging.info(f"🔗 Full Context for OpenAI: {full_context}")

        # 6️⃣ Query OpenAI for a refined session summary (✅ Fixed response handling)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Summarize this conversation while incorporating user preferences for better context."},
                {"role": "user", "content": full_context}
            ]
        )

        if response and hasattr(response, 'choices') and len(response.choices) > 0:
            first_choice = response.choices[0]
            logging.info(f"🔍 OpenAI First Choice Response: {first_choice}")

            # ✅ Handle OpenAI response as both an object and a dictionary
            if isinstance(first_choice, dict) and "message" in first_choice and "content" in first_choice["message"]:
                summary = first_choice["message"]["content"].strip()
            elif hasattr(first_choice, "message") and hasattr(first_choice.message, "content"):
                summary = first_choice.message.content.strip()
            else:
                logging.error(f"❌ Unexpected OpenAI response format: {first_choice}")
                summary = "No relevant details summarized."

            logging.info(f"✅ Generated Session Summary: {summary}")

            return {"role": "assistant", "content": summary, "contact_number": contact_number}

        logging.warning("⚠️ OpenAI did not return a valid summary.")
        return {"role": "assistant", "content": "No relevant details summarized.", "contact_number": contact_number}

    except Exception as e:
        logging.error(f"❌ Error summarizing session: {e}")
        return {"role": "assistant", "content": "Error summarizing session.", "contact_number": contact_number}

    finally:
        cursor.close()
        conn.close()



def save_session_to_db(contact_number, session_summary):
    """
    Save or update session summary in PostgreSQL.
    """
    conn = get_db_connection()
    if not conn:
        logging.error("❌ Database connection failed. Cannot save session summary.")
        return

    try:
        cursor = conn.cursor()

        # ✅ Extract only the summary text if session_summary is a dictionary
        if isinstance(session_summary, dict) and "content" in session_summary:
            session_summary = session_summary["content"]

        # ✅ Ensure it’s a string before saving
        if isinstance(session_summary, list) or isinstance(session_summary, dict):
            session_summary = json.dumps(session_summary)

        cursor.execute('''
            INSERT INTO user_memory (contact_number, memory_key, value, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (contact_number, memory_key) 
            DO UPDATE SET value = EXCLUDED.value, created_at = CURRENT_TIMESTAMP
        ''', (contact_number, 'session_summary', session_summary))

        conn.commit()
        logging.info(f"✅ Session summary saved for {contact_number}")

    except psycopg2.Error as e:
        logging.error(f"❌ Database error while saving session summary: {e}")

    finally:
        cursor.close()
        conn.close()





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
    
def get_highlighted_menu():
    """
    Retrieve the menu and highlight the meal of the day.
    """
    conn = get_db_connection()
    if not conn:
        return {}, None
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT category, item_name, price, highlight
            FROM menu
            WHERE available = TRUE
            ORDER BY category, item_name
        ''')
        menu_items = cursor.fetchall()

        menu = {}
        meal_of_the_day = None

        for category, item_name, price, highlight in menu_items:
            if category not in menu:
                menu[category] = []
            menu[category].append(f"{item_name} - ${price:.2f}")
            if highlight == 1:
                meal_of_the_day = f"{item_name} - ${price:.2f}"
    except psycopg2.Error as e:
        logging.error(f"Database error while fetching menu: {e}")
        menu, meal_of_the_day = {}, None
    finally:
        cursor.close()
        conn.close()

    return menu, meal_of_the_day




def send_daily_menu():
    """Send the daily menu, highlighting the meal of the day."""
    menu, meal_of_the_day = get_highlighted_menu()

    if not menu:
        logging.info("No menu available to send.")
        return

    menu_message = "🌟 * Culinary Delight awaits! Check Out Today's Menu* 🌟\n\n"
    if meal_of_the_day:
        menu_message += f"🍴 *Meal of the Day:* {meal_of_the_day}\n\n"

    for category, items in menu.items():
        menu_message += f"*{category}:*\n" + "\n".join(items) + "\n\n"

    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT contact_number FROM customers")
        customers = cursor.fetchall()

        for customer in customers:
            contact_number = customer[0]
            send_whatsapp_message(contact_number, menu_message)
    except psycopg2.Error as e:
        logging.warning(f"Database error while sending menu: {e}")
    finally:
        cursor.close()
        conn.close()



def get_menu():
    """Retrieve the menu from the database."""
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT category, item_name, price FROM menu WHERE available = TRUE ORDER BY category, item_name')
        menu_items = cursor.fetchall()

        # Organize the menu into categories
        menu = {}
        for category, item_name, price in menu_items:
            if category not in menu:
                menu[category] = []
            menu[category].append(f"{item_name} - ${price:.2f}")

    except psycopg2.Error as e:
        logging.warning(f"Database error while retrieving menu: {e}")
        menu = {}

    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed

    return menu


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


def validate_order(order_details):
    """Validate the ordered items against the menu and check their availability."""
    conn = get_db_connection()
    if not conn:
        return set(), order_details.split(',')

    try:
        cursor = conn.cursor()
        # Split the ordered items into a list
        order_items = [item.strip().lower() for item in order_details.split(',')]

        # Use PostgreSQL's ANY() instead of manual placeholders
        cursor.execute("""
            SELECT LOWER(item_name) FROM menu 
            WHERE LOWER(item_name) = ANY(%s) AND available = TRUE
        """, (order_items,))

        # Fetch available items
        available_items = {row[0] for row in cursor.fetchall()}
    
    except psycopg2.Error as e:
        logging.warning(f"Database error while validating order: {e}")
        available_items = set()
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed

    return available_items, order_items



def save_reservation(name, contact_number, reservation_date, reservation_time, number_of_people, table_number):
    """Save a reservation in the database with reservations_done set to FALSE by default."""
    conn = get_db_connection()
    if not conn:
        return "Database connection failed."

    try:
        cursor = conn.cursor()

        # ✅ Initialize available_tables as an empty list before using it
        available_tables = []

        # Check if the table is available
        cursor.execute('SELECT is_available FROM restaurant_tables WHERE table_number = %s', (table_number,))
        table_status = cursor.fetchone()

        if not table_status:
            return f"Table {table_number} does not exist in our restaurant. Please choose a valid table number."

        if not table_status[0]:  # If the table is unavailable
            cursor.execute('SELECT table_number, capacity FROM restaurant_tables WHERE is_available = TRUE')
            available_tables = cursor.fetchall()

            if not available_tables:  # ✅ Ensure available_tables is checked only after it's assigned a value
                return "Apologies 🥺, all tables are fully booked. Please check back later or contact us for assistance."

            options = "\n".join([f"Table {table[0]} (Capacity: {table[1]})" for table in available_tables])
            return f"Apologies 🥺, Table {table_number} is already booked. Please choose another table from remaining options:\n{options}\nNB* Please resend your template message with the new table number"

        # Save the reservation with reservations_done set to FALSE
        cursor.execute('''
            INSERT INTO reservations (name, contact_number, reservation_time, number_of_people, table_number, reservations_done)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, contact_number, f"{reservation_date} at {reservation_time}", number_of_people, table_number, False))

        # Mark the table as unavailable
        cursor.execute('UPDATE restaurant_tables SET is_available = FALSE WHERE table_number = %s', (table_number,))
        conn.commit()

        notification_message = (
            f"New Reservation Alert:\n\n"
            f"Name: {name}\n"
            f"Contact Number: {contact_number}\n"
            f"Time: {reservation_date} at {reservation_time}\n"
            f"Number of People: {number_of_people}\n"
            f"Table Number: {table_number}\n"
            f"Status: Pending (Not yet completed)"
        )
        send_whatsapp_message(ADMIN_NUMBER, notification_message)

        return f"Success! Booking confirmed for {name} on {reservation_date} at {reservation_time} for {number_of_people} people at table {table_number}."
    
    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        return "Error saving reservation."
    finally:
        cursor.close()
        conn.close()

    
def cancel_reservation(contact_number, table_number):
    """
    Cancel a reservation and mark the table as available.
    """
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        return "Database connection failed."

    try:
        cursor = conn.cursor()

        # Check if the reservation exists
        cursor.execute('SELECT contact_number FROM reservations WHERE table_number = %s', (table_number,))
        reservation = cursor.fetchone()

        if not reservation:
            return f"❌ No active reservation found for table {table_number}."
        
        if reservation[0] != contact_number:
            return f"❌ You are not authorized to cancel this reservation."
        
        # Delete the reservation
        cursor.execute('DELETE FROM reservations WHERE table_number = %s AND contact_number = %s', (table_number, contact_number))

        # Mark the table as available
        cursor.execute('UPDATE restaurant_tables SET is_available = TRUE WHERE table_number = %s', (table_number,))

        conn.commit()
        return f"✅ Reservation for table {table_number} has been successfully canceled."
    
    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        return "There was an issue canceling the reservation. Please try again later."
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed




def save_order(contact_number, order_details, delivery="No", delivery_name=None, delivery_location=None, delivery_time=None):
    """Save an order in the database."""
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        return "Database connection failed."

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (contact_number, order_details, delivery, delivery_name, delivery_location, delivery_time)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (contact_number, order_details, delivery, delivery_name, delivery_location, delivery_time))
        conn.commit()

        # Notify admin about the new order
        notification_message = (
            f"New Order Alert:\n\n"
            f"Contact Number: {contact_number}\n"
            f"Order Details: {order_details}\n"
            f"Delivery: {delivery}\n"
            f"Delivery Name: {delivery_name or 'N/A'}\n"
            f"Delivery Location: {delivery_location or 'N/A'}\n"
            f"Delivery Time: {delivery_time or 'N/A'}"
        )
        send_whatsapp_message(ADMIN_NUMBER, notification_message)

        return "✅ Your order has been successfully saved."
    
    except psycopg2.Error as e:
        logging.error(f"Database error while saving order: {e}")
        return "❌ There was an issue saving your order. Please try again later."
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed


def cancel_order(contact_number, order_details):
    """
    Cancel an order by changing its status to 'cancelled' if the status is still 'received'.
    """
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        return "Database connection failed."

    try:
        cursor = conn.cursor()

        # Check if the order exists and is in 'received' status
        cursor.execute('''
            SELECT id FROM orders
            WHERE contact_number = %s AND order_details = %s AND status = 'received'
        ''', (contact_number, order_details))
        order = cursor.fetchone()

        if not order:
            return (
                f"❌ Sorry, no order for '{order_details}' with contact number '{contact_number}' "
                "is in 'received' status. Orders in 'in-transit' cannot be canceled."
            )

        # Update the order status to 'cancelled'
        cursor.execute('''
            UPDATE orders
            SET status = 'cancelled'
            WHERE contact_number = %s AND order_details = %s
        ''', (contact_number, order_details))

        conn.commit()
        return f"✅ Your order for '{order_details}' under {contact_number} has been successfully canceled."
    
    except psycopg2.Error as e:
        logging.error(f"Database error while canceling order: {e}")
        return "❌ There was an issue canceling your order. Please try again later."
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed



# Log new conversation or updates in the database
def log_conversation(from_number, message, bot_reply, status):
    """
    Log customer conversations in the database.
    """
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        logging.info("❌ Database connection failed. Cannot log conversation.")
        return

    try:
        cursor = conn.cursor()
        logging.info(f"📝 Logging conversation: {from_number} - {message} - {bot_reply} - {status}")
        cursor.execute('''
            INSERT INTO restaurant (from_number, message, bot_reply, status, reported)
            VALUES (%s, %s, %s, %s, 0)
        ''', (from_number, message, bot_reply, status))
        conn.commit()
        logging.info("✅ Conversation logged successfully.")
    
    except psycopg2.Error as e:
        logging.warning(f"Database error while logging conversation: {e}")
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed



def get_user_status(contact_number):
    """
    Retrieve the status of a customer based on their contact number.
    """
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        return 'new'  # Default to 'new' if connection fails

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM customers WHERE contact_number = %s', (contact_number,))
        row = cursor.fetchone()

        if row:
            logging.info(f"Debug: Status fetched for {contact_number}: {row[0]}")
            return row[0]
        else:
            logging.debug(f"Debug: No record found for {contact_number}. Defaulting to 'new'")
            return 'new'
    
    except psycopg2.Error as e:
        logging.error(f"Database error while fetching status: {e}")
        return 'new'  # Default to 'new' on error
    
    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed


def update_user_status(contact_number, status):
    """
    Add or update the status of a customer in the database.
    """
    conn = get_db_connection()  # Use PostgreSQL connection
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO customers (contact_number, status)
            VALUES (%s, %s)
            ON CONFLICT (contact_number) DO UPDATE SET status = %s
        ''', (contact_number, status, status))
        conn.commit()
        logging.info(f"Debug: Updated status for {contact_number} to {status}")

    except psycopg2.Error as e:
        logging.error(f"Database error while updating status: {e}")

    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed




def send_intro_to_new_customers():
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT contact_number FROM customers WHERE status = 'new'")
        new_customers = cursor.fetchall()

        if not new_customers:
            logging.info("✅ No new customers to process.")
            return

        for customer in new_customers:
            contact_number = customer[0]

            # Validate phone number
            if not is_valid_phone_number(contact_number):
                logging.warning(f"⚠️ Invalid phone number: {contact_number}. Skipping...")
                continue

            logging.info(f"📨 Processing customer: {contact_number}")

            # Retrieve customer name
            customer_name = get_customer_name(contact_number) or "Customer"

            # Define header image
            header_image_url = "https://drive.google.com/uc?id=1epvMKHgTqnzD8DSYHuvaApg3HJSTk1Xt"

            # Send WhatsApp template message
            try:
                response_json = send_template_message(
                    to=contact_number,
                    template_name="introductory_message",
                    template_variables={"customer_name": customer_name},  # ✅ Correctly passing named parameter
                    header_image_url=header_image_url
                )

                # Log the API response for debugging
                logging.debug(f"📡 API Response for {contact_number}: {response_json}")

                if response_json and response_json.get("messages"):
                    update_user_status(contact_number, 'existing')
                    logging.info(f"🔄 Status updated to 'existing' for {contact_number}")
                else:
                    logging.error(f"❌ Failed to send message to {contact_number}: {response_json}")

            except Exception as e:
                logging.error(f"❌ Error sending template message to {contact_number}: {e}")

            # Optional delay to avoid API rate limiting
            time.sleep(1)

        logging.info("✅ Introductory messages sent to all new customers.")

    except psycopg2.Error as db_error:
        logging.error(f"❌ Database error: {db_error}")

    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")

    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed



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


def get_customer_name(contact_number):
    """
    Retrieve the customer's name from the database using their WhatsApp number.
    """
    try:
        # Ensure we're querying with the correct phone number
        if contact_number.startswith('whatsapp:'):
            contact_number = contact_number.replace('whatsapp:', '')

        # Normalize contact number (Ensure +.. format)
        if not contact_number.startswith('+'):
            contact_number = f"+{contact_number}"

        conn = get_db_connection()  # Use PostgreSQL connection
        if not conn:
            return "Guest"  # Return a default name if connection fails

        cursor = conn.cursor()
        logging.debug(f"Debug: Querying database with contact_number: {contact_number}")
        cursor.execute('SELECT name FROM customers WHERE contact_number = %s', (contact_number,))
        row = cursor.fetchone()

        if row and row[0]:
            return row[0]
        else:
            logging.debug(f"Debug: No matching record found for {contact_number}")
            return "Guest"  # Return a default name instead of None

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching name: {e}")
        return "Guest"

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return "Guest"

    finally:
        cursor.close()
        conn.close()  # Ensure connection is closed




def is_valid_phone_number(phone_number): 
    """ Validate international phone numbers (E.164 format). """
    pattern = re.compile(r"^\+[1-9]\d{6,14}$")  # Correct E.164 format
    return bool(pattern.match(phone_number))

# Query OpenAI API
def query_openai_model(user_message, session_summary, formatted_history):
    try:
        logging.debug(f"Debug: Querying OpenAI API with -> {user_message}")

        # Fetch the daily menu
        daily_menu = get_menu()  # Use your get_menu() function
        if not daily_menu:
            menu_text = "Menu is currently unavailable. Please try again later."
        else:
            # Format the menu into a readable string
            menu_text = "\n".join(
                f"{category}:\n" + "\n".join(items) for category, items in daily_menu.items()
            )
            

        # System role definition
        system_role = {
            "role": "system",
            "content": (
                "You are Taguta, a highly intelligent and friendly customer assistant for Star Restaurant, "
                "a renowned establishment known for its exceptional dining experiences. "
                "Star Restaurant is located at 123 Drive Harare, with the best chefs and 8 friendly waitresses. "
                "We value kindness, quality, and fun. Your primary goal is to assist customers with orders, "
                "booking, and general questions. You maintain efficiency, politeness, and professionalism.\n\n"
                 "📌 **Context from Previous Messages:**\n"
                f"{session_summary}\n\n"
                "📜 **Full Conversation History:**\n"
                f"{formatted_history}\n\n"
                "🔵 **Current User Message:**\n"
                f"User: {user_message}\n\n"
                 "Your response should continue the conversation smoothly.\n\n"  

                "1. **Greeting Customers**\n"
                "   - Greet customers warmly with their name during the first interaction.\n"
                "   - Avoid repeating introductory greetings unless explicitly asked.\n\n"

                "2. **Handling Orders**\n"
                "   - Users can only order from the current menu.\n"
                f"   - Today's menu:\n{menu_text}\n\n"
                " If they want to place an order send them this\n\n"
                "   'Absolutely!, I'd be glad to make an order for you. Simply type place order and I will walk you through the whole process.\n***Remember you can only order from available menu items, If you like I can show you available menu items, simply type show menu, to see  whats available before placing an order'"

                "3. **Table Bookings**\n"
                "   - Total number of tables: **1,2,3,4,5**.\n"
                "     - Tables **1-3 are indoors**, Tables **4-5 are outdoors**.\n"
                "   - If a user wants to make a reservation, send them this"
                "   'I'd be glad to make a reservation for you! if you are using WHATSAPP on your laptop simply type book table and I will walk you through the process. If you are using, your phone type reserve table'"
                "4. **Sharing Menu Information**\n"
                f"   - Today's menu:\n{menu_text}\n\n"

                "5. **Providing Support for Special Requests**\n"
                "   - Handle customer queries about allergies, preferences, or special occasions.\n"
                "   - Example: 'Certainly! Let me know if you have any dietary preferences or special requests, and I will assist you accordingly.'\n\n"

                "6. **Cancelling Orders and Reservations**\n"
                "   - Users can cancel an order if it is not in transit.\n"
                "   - If an order is in transit, inform them that it cannot be canceled.\n"
                "   - Provide the correct format to cancel an order:\n"
                "     'Cancel order for [Order Details]' (e.g., 'Cancel order for cheesecake')\n"
                "   - Reservations can only be canceled from the number used to book.\n"
                "   - Provide the format to cancel a reservation:\n"
                "     'Cancel reservation for table [Table Number]' (e.g., 'Cancel reservation for table 4')\n\n"

                "7. **Resolving Unclear Messages**\n"
                "   - If a message is unclear, politely ask for clarification.\n\n"

                "8. **Using OpenAI API for Uncommon Questions**\n"
                "   - When faced with unique questions or unsupported requests, leverage the OpenAI API for intelligent responses.\n"
                "   - Example response: 'Umm...!'\n\n"

                "9. **Tone and Personality**\n"
                "   - Maintain a polite, friendly, and professional tone.\n"
                "   - Express gratitude frequently to build a positive rapport.\n"
                "   - Add the customer's name to the farewell message.\n"
                "   - Example: 'Thank you for choosing Star Restaurant, [Customer Name]! We are delighted to assist you!'\n"
                "   - Stay patient and adaptable to customer needs."
              
            )
        }
            
        


        # Query OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                system_role,
                {"role": "user", "content": user_message}
            ]
        ) 
        
        logging.info(f"Debug: OpenAI Response -> {response}")
        
        # Extract the first message from the assistant's reply
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
        else:
            return "Unexpected response format from the OpenAI API."

    except Exception as e:
        logging.error(f"Error querying OpenAI API: {e}")
        return "There was an error processing your request. Please try again later."



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



def parse_datetime(date_str, time_str):
    """Parse user input for date and time."""
    try:
        # Add current year to the date string
        current_year = datetime.now().year
        combined_date_time = f"{date_str} {current_year} {time_str}"
        # Parse the combined string into a datetime object
        parsed_datetime = datetime.strptime(combined_date_time, "%d %B %Y %I%p")
        return parsed_datetime
    except ValueError:
        return None


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



def process_order_flow(response_data, message):
    """
    Processes orders placed via WhatsApp Flow, handling both delivery and pickup.
    """
    from_number = message.get("from", "")

    # ✅ Fix: Ensure 'screen' key exists before using it
    screen_name = response_data.get("screen", "UNKNOWN_SCREEN")
    logging.info(f"🔍 Received screen: {screen_name}")

    # ✅ Extract Order Details from Flow
    order_items = response_data.get("screen_0_Order_Item_0", [])  # Extract order items as a list
    # ✅ Fix: Ensure each item has an underscore before splitting
    order_details = ", ".join([item.split("_", 1)[1] if "_" in item else item for item in order_items])

    delivery_status = "delivery" if response_data.get("screen_0_Delivery_1", "") == "0_Yes" else "pickup"
    delivery_name = response_data.get("screen_1_Name_0", "").strip()

    # ✅ Fix: Use try/except to avoid crashes when 'screen_1_Location_1' is missing
    try:
        delivery_location = response_data["screen_1_Location_1"].strip()
    except KeyError:
        delivery_location = "Not Required"

    # ✅ Fix: Ensure missing time does not crash the system
    delivery_time = response_data.get("screen_1_Time_2", "max")
    delivery_time = delivery_time.strip() if isinstance(delivery_time, str) else "max"

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
        bot_reply = (
            f"❌ The following items are not available: {', '.join(unavailable_items)}.\n"
            "Please retry your order with available menu items."
        )
    else:
        # ✅ Save the order based on delivery status
        if delivery_status == "pickup":
            save_order(
                contact_number=from_number,
                order_details=", ".join(available_items),
                delivery="No"
            )
            bot_reply = f"✅ Your order for {', '.join(available_items)} has been placed successfully. No delivery required."

        elif delivery_status == "delivery":
            save_order(
                contact_number=from_number,
                order_details=", ".join(available_items),
                delivery="Yes",
                delivery_name=delivery_name,
                delivery_location=delivery_location,
                delivery_time=delivery_time
            )
            bot_reply = f"🚚 Order Confirmed! Your {', '.join(available_items)} will be delivered!"

            #bot_reply = f"🚚 Order Confirmed! Your {', '.join(available_items)} will be delivered to {delivery_location} at {delivery_time}."

    # ✅ Send Confirmation
    send_whatsapp_message(from_number, bot_reply)
    return "Message processed.", 200





def process_reservation_flow(response_data, message):
    """
    Processes table reservations from WhatsApp Flow responses.
    """
    from_number = message.get("from", "")
    
    # ✅ Extract Data
    name = response_data.get("name")
    reservation_date = response_data.get("reservation_date")
    reservation_time_raw = response_data.get("reservation_time")
    number_of_people = response_data.get("number_of_people")
    table_number_raw = response_data.get("table_number", "")

    # ✅ Extract and clean time
    time_match = re.search(r'(\d{1,2}(?:am|pm))', reservation_time_raw)
    reservation_time = time_match.group() if time_match else "Invalid time"

    # ✅ Extract table number
    table_number_match = re.search(r'\d+', table_number_raw)
    table_number = int(table_number_match.group()) + 1 if table_number_match else None

    if table_number is None:
        logging.warning(f"⚠️ Invalid table number received: {table_number_raw}")
        return jsonify({"error": "Invalid table number. Please choose a valid table."}), 400

    logging.info(f"✅ Reservation - Name: {name}, Date: {reservation_date}, Time: {reservation_time}, People: {number_of_people}, Table: {table_number}")

    # ✅ Save the reservation
    bot_reply = save_reservation(name, from_number, reservation_date, reservation_time, number_of_people, table_number)

    # ✅ Send confirmation
    send_whatsapp_message(from_number, bot_reply)

    return jsonify({"message": "Booking processed"}), 200


def process_order_rating_flow(response_data, message):
    """
    Processes order ratings from WhatsApp Flow responses.
    """
    from_number = message.get("from", "")

    # ✅ Extract rating from the correct key (e.g., "screen_0_Order_experience_0")
    rating_text = next(
        (value for key, value in response_data.items() if "Order_experience" in key), None
    )

    if not rating_text:
        logging.warning("⚠️ No rating found in response JSON.")
        return jsonify({"error": "No rating found."}), 400

    logging.info(f"📥 Received rating response from {from_number}: {rating_text}")

    # ✅ Extract the correct number (from "4/5" instead of "1_" or other numbers)
    match = re.findall(r'(\d+)', rating_text)  # Find all numbers
    if not match or len(match) < 2:
        logging.warning(f"⚠️ Invalid rating format received: {rating_text}")
        return jsonify({"error": "Invalid rating format"}), 400

    rating = int(match[1])  # ✅ Always take the **middle** number (correct rating)

    if rating < 1 or rating > 5:
        logging.warning(f"⚠️ Invalid rating value detected: {rating}")
        return jsonify({"error": "Invalid rating value. Please provide a rating between 1 and 5."}), 400

    # ✅ Connect to database
    conn = get_db_connection()
    if not conn:
        logging.error("❌ Database connection failed.")
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # ✅ Find the most recent completed order for the user
        cursor.execute('''
            SELECT id FROM orders 
            WHERE contact_number = %s AND status = 'done' 
            ORDER BY created_at DESC LIMIT 1
        ''', (from_number,))
        order = cursor.fetchone()

        if order:
            order_id = order[0]  # ✅ Extract order ID dynamically
            logging.info(f"🔍 Found completed order for rating: {order_id}")

            # ✅ Update the order rating
            cursor.execute('UPDATE orders SET rating = %s WHERE id = %s', (rating, order_id))
            conn.commit()
            logging.info(f"✅ Successfully updated order {order_id} with rating {rating}")

            bot_reply = f"⭐ Thank you for rating your order {rating}/5! We appreciate your feedback. 😊"
        
        else:
            logging.warning(f"⚠️ No completed orders found for user {from_number}.")
            bot_reply = (
                "We couldn't find a completed order to rate. "
                "Please ensure your order is marked as 'completed' before rating."
            )

    except psycopg2.Error as e:
        logging.error(f"❌ Database error while updating rating: {e}")
        bot_reply = "An error occurred while processing your rating. Please try again later."

    finally:
        cursor.close()
        conn.close()
        logging.info("🔚 Database connection closed.")

    send_whatsapp_message(from_number, bot_reply)
    return jsonify({"message": bot_reply}), 200


def process_reservation_rating_flow(response_data, message):
    """
    Processes reservation ratings from WhatsApp Flow responses.
    """
    from_number = message.get("from", "")
    
    # ✅ Extract rating from the correct key (e.g., "screen_0_Dining_Experience_0")
    rating_text = next(
        (value for key, value in response_data.items() if "Dining_Experience" in key), None
    )

    if not rating_text:
        logging.warning("⚠️ No rating found in response JSON.")
        return jsonify({"error": "No rating found."}), 400

    logging.info(f"📥 Received reservation rating response from {from_number}: {rating_text}")

 
    match = re.findall(r'(\d+)', rating_text)  # ✅ Find all numbers
    if not match:
        logging.warning(f"⚠️ Invalid reservation rating format received: {rating_text}")
        return jsonify({"error": "Invalid rating format"}), 400

    rating = int(match[1])  # ✅ Always take the last number (e.g., from "2_★★★☆☆_•_Average_(3/5)" → `3`)

    if rating < 1 or rating > 5:
        logging.warning(f"⚠️ Invalid rating value detected: {rating}")
        return jsonify({"error": "Invalid rating value. Please provide a rating between 1 and 5."}), 400


    # ✅ Connect to database
    conn = get_db_connection()
    if not conn:
        logging.error("❌ Database connection failed.")
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # ✅ Find the most recent completed reservation for the user
        cursor.execute('''
            SELECT id FROM reservations 
            WHERE contact_number = %s AND reservations_done = TRUE
            ORDER BY created_at DESC LIMIT 1
        ''', (from_number,))
        reservation = cursor.fetchone()

        if reservation:
            reservation_id = reservation[0]  # ✅ Extract reservation ID dynamically
            logging.info(f"🔍 Found completed reservation for rating: {reservation_id}")

            # ✅ Update the reservation rating
            cursor.execute('UPDATE reservations SET rating = %s WHERE id = %s', (rating, reservation_id))
            conn.commit()
            logging.info(f"✅ Successfully updated reservation {reservation_id} with rating {rating}")

            bot_reply = f"⭐ Thank you for rating your reservation {rating}/5! We appreciate your feedback. 😊"
        
        else:
            logging.warning(f"⚠️ No completed reservations found for user {from_number}.")
            bot_reply = (
                "We couldn't find a completed reservation to rate. "
                "Please ensure your reservation is marked as 'completed' before rating."
            )

    except psycopg2.Error as e:
        logging.error(f"❌ Database error while updating reservation rating: {e}")
        bot_reply = "An error occurred while processing your rating. Please try again later."

    finally:
        cursor.close()
        conn.close()
        logging.info("🔚 Database connection closed.")

    send_whatsapp_message(from_number, bot_reply)
    return jsonify({"message": bot_reply}), 200



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
                        incoming_message, session_summary, formatted_history
                    )
                elif any(farewell in incoming_message.lower() for farewell in ["bye", "goodbye", "see you", "take care"]):
                    # Append name to farewell
                    bot_reply = query_openai_model(
                        incoming_message, session_summary, formatted_history
                    ) + f" Goodbye {get_customer_name(from_number)}!"
                else:
                    
                    bot_reply = query_openai_model(incoming_message, session_summary, formatted_history)
            
                log_conversation(from_number, incoming_message, bot_reply, "processed")

              
                send_whatsapp_message(from_number, bot_reply)
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



def check_inactivity(from_number):
    """
    Check if the user has been inactive for more than 30 minutes and update session memory if needed.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Retrieve the last message timestamp
        cursor.execute('''
            SELECT timestamp FROM restaurant
            WHERE from_number = %s
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (from_number,))
        last_activity = cursor.fetchone()

        if not last_activity:
            logging.info(f"🔍 No previous activity found for {from_number}. Skipping inactivity check.")
            return

        last_activity_time = last_activity[0]
        inactive_duration = datetime.now() - last_activity_time

        # If user has been inactive for more than 30 minutes, summarize session
        if inactive_duration > timedelta(minutes=30):
            session_summary = summarize_session(from_number)
            save_session_to_db(from_number, session_summary)
            logging.info(f"🔄 Session for {from_number} summarized due to inactivity.")

    except psycopg2.Error as e:
        logging.error(f"Database error while checking inactivity: {e}")

    finally:
        cursor.close()
        conn.close()





@app.route('/status-callback', methods=['POST'])
def status_callback():
    try:
        message_status = request.values.get('MessageStatus', '')
        message_sid = request.values.get('MessageSid', '')
        logging.info(f"Message SID: {message_sid}, Status: {message_status}")
        return "Status received", 200
    except Exception as e:
        logging.error(f"Error in status callback: {e}")
        return f"Internal Server Error: {e}", 500

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
schedule.every(2).minutes.do(send_intro_to_new_customers)

#Schedule Bulk Messaging 
schedule.every().day.at("09:00").do(send_daily_menu)
#schedule.every(1).minute.do(send_daily_menu)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    init_db()
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=5000)
