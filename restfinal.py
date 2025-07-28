import os
import re
import sqlite3
import schedule
import time
import threading
from flask import Flask, request, session, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import requests
from flask_session import Session
from datetime import datetime, timedelta



# Set up environment variables for Meta API
os.environ['META_PHONE_NUMBER_ID'] = '531242683411454'
os.environ['META_ACCESS_TOKEN'] = 'EAAJFxCsSeekBO5RXVrhk2ptckttv20rEMKcZAhOriMEYc4GRIZCkiJORNd6dAlPVvkU10XtynbtYso5IcY0QC7QkBoFKaAmwLZArsOZBVcaaKQ6jJwXir63bqnvZCj7I24phhlaehPI2ZAqfyYSwqZBAXeamZCogZCZARBRWANZCDxWJrRX3dU2q6od7cVGFRYS1RZBTV56XYwnuj8PDrvMuo9ZAIEIq7odffWgMtXfWTIq3Y'
os.environ['OPENAI_API_KEY'] = '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' 



 #Initialize OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)


# Flask application
app = Flask(__name__)

# Configure Flask-Session
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem for development
app.config['SESSION_PERMANENT'] = False  # Sessions will not expire unless explicitly cleared
#app.secret_key = 'ghnvdre5h4562' 
Session(app)



# Admin number to send periodic updates
ADMIN_NUMBER = '+263773344079'

# Initialize the SQLite database for conversation logging
def init_db():
    with sqlite3.connect('restaurant.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restaurant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_number TEXT NOT NULL,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bot_reply TEXT,
                status TEXT,
                reported INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contact_number TEXT NOT NULL,
                reservation_time DATETIME NOT NULL,
                number_of_people INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_number TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contact_number, key) ON CONFLICT REPLACE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_number TEXT NOT NULL,
                order_details TEXT NOT NULL,
                delivery TEXT DEFAULT 'No', 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
                       ''')
        conn.commit()



def get_user_preferences(contact_number):
    """
    Retrieve user preferences and memory from the database.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM user_memory WHERE contact_number = ?', (contact_number,))
            preferences = {row[0]: row[1] for row in cursor.fetchall()}
            return preferences
    except sqlite3.Error as e:
        print(f"Database error while retrieving preferences: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {}

def summarize_session(conversation, contact_number):
    """
    Summarize the conversation session to provide context for responses.
    """
    try:
        # Retrieve user preferences
        preferences = get_user_preferences(contact_number)
        # Combine all messages into a single string for summarization
        preferences_summary = ", ".join([f"{key}: {value}" for key, value in preferences.items()])
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation])

        # Construct the full context
        context = f"User preferences: {preferences_summary}\n\nConversation history:\n{conversation_text}"
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Summarize this conversation to provide context for future responses."},
                {"role": "user", "content": context}
            ]
        )
        if response.choices:
            return response.choices[0].message.content.strip()
        return "No relevant details summarized."
    except Exception as e:
        print(f"Error summarizing session: {e}")
        return "Error summarizing session."


def save_session_to_db(contact_number, session_summary):
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_memory (contact_number, key, value)
                VALUES (?, ?, ?)
            ''', (contact_number, 'session_summary', session_summary))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")



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
        print(f"Error ending session: {e}")
        return "Error ending session."
    
def get_highlighted_menu():
    """
    Retrieve the menu and highlight the meal of the day.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT category, item_name, price, highlight
                FROM menu
                WHERE available = 1
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

            return menu, meal_of_the_day
    except sqlite3.Error as e:
        print(f"Database error while fetching menu: {e}")
        return {}, None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {}, None


def send_daily_menu():
    """
    Send the daily menu, highlighting the meal of the day.
    """
    try:
        menu, meal_of_the_day = get_highlighted_menu()

        if not menu:
            print("No menu available to send.")
            return

        menu_message = "🌟 * Culinary Delight awaits! Check Out Today's Menu* 🌟\n\n"
        if meal_of_the_day:
            menu_message += f"🍴 *Meal of the Day:* {meal_of_the_day}\n\n"

        for category, items in menu.items():
            menu_message += f"*{category}:*\n" + "\n".join(items) + "\n\n"

        # Fetch all user numbers from the database
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT contact_number FROM customers")
            customers = cursor.fetchall()

        # Send menu to all customers
        for customer in customers:
            contact_number = customer[0]
            send_whatsapp_message(contact_number, menu_message)

        print("Daily menu messages sent successfully.")
    except Exception as e:
        print(f"Error sending daily menu: {e}")


def get_menu():
    """
    Retrieve the menu from the database.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT category, item_name, price FROM menu WHERE available = 1 ORDER BY category, item_name')
            menu_items = cursor.fetchall()

            # Organize the menu into categories
            menu = {}
            for category, item_name, price in menu_items:
                if category not in menu:
                    menu[category] = []
                menu[category].append(f"{item_name} - ${price:.2f}")

            return menu
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {}



#save reservation in database 
def save_reservation(name, contact_number, reservation_time, number_of_people, table_number):
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()

            # Check if the table is available
            cursor.execute('SELECT is_available FROM restaurant_tables WHERE table_number = ?', (table_number,))
            table_status = cursor.fetchone()

            if not table_status:
                return f"Table {table_number} is not in our restaurant. Please choose a valid table number."
            if table_status[0] == 0:
                cursor.execute('SELECT table_number, capacity FROM restaurant_tables WHERE is_available = 1')
                available_tables = cursor.fetchall()
                
                # Format the available tables into a message
                if available_tables:
                    options = "\n".join([f"Table {table[0]} (Capacity: {table[1]})" for table in available_tables])
                    return f"Apologies 🥺, Table {table_number} is already booked. Please choose another table from the remaining:\n{options}"
                else:
                    return "Apologies!🥺, Table {table_number} is already booked, and no other tables are available at the moment"

            cursor.execute('''
                INSERT INTO reservations (name, contact_number, reservation_time, number_of_people, table_number)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, contact_number, reservation_time, number_of_people, table_number))

             # Mark the table as unavailable
            cursor.execute('UPDATE restaurant_tables SET is_available = 0 WHERE table_number = ?', (table_number,))

            conn.commit()

            # Send a notification to the admin number
            notification_message = (
                f"New Reservation Alert:\n\n"
                f"Name: {name}\n"
                f"Contact Number: {contact_number}\n"
                f"Time: {reservation_time}\n"
                f"Number of People: {number_of_people}\n"
                f"Table Number: {table_number}\n"
            )
            send_whatsapp_message(ADMIN_NUMBER, notification_message)
            
            return "Your reservation has been successfully saved."
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return "There was an issue saving your reservation. Please try again later."
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "An unexpected error occurred. Please try again later."
    
def cancel_reservation(table_number):
    """
    Cancel a reservation and mark the table as available.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()

            # Delete the reservation
            cursor.execute('DELETE FROM reservations WHERE table_number = ?', (table_number,))

            # Mark the table as available
            cursor.execute('UPDATE restaurant_tables SET is_available = 1 WHERE table_number = ?', (table_number,))

            conn.commit()
            return f"Reservation for table {table_number} has been canceled."
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return "There was an issue canceling the reservation. Please try again later."
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "An unexpected error occurred. Please try again later."



def save_order(contact_number, order_details, delivery="No", delivery_name=None, delivery_location=None, delivery_time=None):
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO orders (contact_number, order_details, delivery, delivery_name, delivery_location, delivery_time)
                VALUES (?, ?, ?, ?, ?, ?)
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

            return "Your order has been successfully saved."
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return "There was an issue saving your order. Please try again later."
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "An unexpected error occurred. Please try again later."

def cancel_order(contact_number, order_details):
    """
    Cancel an order by changing its status to 'cancelled' if the status is still 'received'.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()

            # Check if the order exists and is in 'received' status
            cursor.execute('''
                SELECT * FROM orders
                WHERE contact_number = ? AND order_details = ? AND status = 'received'
            ''', (contact_number, order_details))
            order = cursor.fetchone()

            if not order:
                return (
                    f"Sorry, no order for '{order_details}' with contact number '{contact_number}' "
                    "is in 'received' status. Orders in 'in-transit' cannot be canceled."
                )

            # Update the order status to 'cancelled'
            cursor.execute('''
                UPDATE orders
                SET status = 'cancelled'
                WHERE contact_number = ? AND order_details = ?
            ''', (contact_number, order_details))

            conn.commit()
            return f"Your order for '{order_details}' has been successfully canceled."
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return "There was an issue canceling your order. Please try again later."
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "An unexpected error occurred. Please try again later."




# Log new conversation or updates in the database
def log_conversation(from_number, message, bot_reply, status):
    """
    Log customer conversations in the database.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO restaurant (from_number, message, bot_reply, status, reported)
                VALUES (?, ?, ?, ?, 0)
            ''', (from_number, message, bot_reply, status))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")




def get_user_status(contact_number):
    """
    Retrieve the status of a customer based on their contact number.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM customers WHERE contact_number = ?', (contact_number,))
            row = cursor.fetchone()
            if row:
                print(f"Debug: Status fetched for {contact_number}: {row[0]}")
                return row[0]
            else:
                print(f"Debug: No record found for {contact_number}. Defaulting to 'new'")
                return 'new'
    except sqlite3.Error as e:
        print(f"Database error while fetching status: {e}")
        return 'new'

def update_user_status(contact_number, status):
    """
    Add or update the status of a customer in the database.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO customers (contact_number, status)
                VALUES (?, ?)
                ON CONFLICT(contact_number) DO UPDATE SET status = ?
            ''', (contact_number, status, status))
            conn.commit()
            print(f"Debug: Updated status for {contact_number} to {status}")
    except sqlite3.Error as e:
        print(f"Database error while updating status: {e}")



def send_intro_to_new_customers():
    """
    Send an introductory messages to all new customers 
    and update their status to existing.
    """
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT contact_number FROM customers WHERE status = 'new'")
            new_customers = cursor.fetchall()

            if not new_customers:
                print("No new customers found.")
                return

            for customer in new_customers:
                contact_number = customer[0]

                # Validate phone number
                if not is_valid_phone_number(contact_number):
                    print(f"Invalid phone number: {contact_number}. Skipping...")
                    continue

                print(f"Processing contact: {contact_number}")

                # Generate an introductory message using OpenAI
                try:
                    intro_message = (
                        "Hello, I am Taguta, your friendly customer assistant at Star Restaurant."
                        "I'm here to introduce you to our exceptional dining experience that blends exquisite cuisine, a warm atmosphere, and top-notch service."
                        "and Whether it's a romantic dinner, a family gathering, or a special celebration, we strive to make every meal memorable." 
                        "Please feel free to ask any questions, explore our menu, or make a reservation—I'm here to assist you every step of the way!"
                        "and Thank you for considering Star Restaurant; we look forward to serving you soon!"
                    )

                    # Send the message via WhatsApp
                    send_whatsapp_message(contact_number, intro_message)

                    # Update status to 'existing'
                    update_user_status(contact_number, 'existing')
                    print(f"Status updated to 'existing' for {contact_number}")

                except Exception :
                    print(f"Error generating introductory message for {contact_number}")

                # Optional: Throttle messages
                time.sleep(1)

            print("Introductory messages sent to new customers.")
    except sqlite3.Error as db_error:
        print(f"Database error: {db_error}")
    except Exception as e:
        print(f"Unexpected error: {e}")

@app.route('/clear-session', methods=['GET'])
def clear_session():
    """
    Clear the entire session.
    """
    try:
        session.clear()  # Clear all session variables
        return "Session has been cleared.", 200
    except Exception as e:
        print(f"Error clearing session: {e}")
        return "Error clearing session.", 500


def get_customer_name(contact_number):
    """
    Retrieve the customer's name from the database.
    """
    try:
        # Remove the "whatsapp:" prefix if it exists
        if contact_number.startswith('whatsapp:'):
            contact_number = contact_number[9:]
        
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            print(f"Debug: Querying database with contact_number: {contact_number}")
            cursor.execute('SELECT name FROM customers WHERE contact_number = ?', (contact_number,))
            row = cursor.fetchone()
            print(f"Debug: Query result: {row}")
            if row and row[0]:
                return row[0]
            else:
                print(f"Debug: No matching record found for {contact_number}")
                return "there"
    except sqlite3.Error as e:
        print(f"Database error while fetching name: {e}")
        return "there"
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "there"



def is_valid_phone_number(phone_number):
    """
    Validate phone number format (E.164) and length.
    """
    pattern = re.compile(r"^\+?[1-9]\d{1,14}$")
    return pattern.match(phone_number) is not None

# Query OpenAI API
def query_openai_model(user_message):
    try:
        print(f"Debug: Querying OpenAI API with -> {user_message}", flush=True)
        
        # System role definition
        system_role = {
    "role": "system",
    "content": (
        "You are Taguta, a highly intelligent and friendly customer assistant for Star Restaurant, "
        "a renowned establishment known for its exceptional dining experiences.Your primary goal is "
        "to assist customers with orders, booking and general questions. You mantain efficiency, politeness, and professionalism.Your responsibilities include:\n\n"
        "1. Greet customers only during the first interaction:\n"
        "Avoid repeating introductory greetings unless explicitly asked. "
        "2. Handling Orders\n"
        "   - Guide customers on how to place an order, providing examples if needed:\n"
        "     'To place an order, simply type: \"Order: Cheesecake, Garlic Bread, and Wine.\" I will confirm your "
        "order and log it for preparation.'\n"
        "   - Confirm their order and thank them for choosing Star Restaurant:\n"
        "     'Thank you! Your order for Cheesecake, Garlic Bread, and Wine has been received. We will prepare it shortly!'\n\n"
        "3. Table Bookings\n"
        "   - Assist with table reservations by providing clear instructions:\n"
        "   -Check if the requested table is available. If unavailable, recommend another table"
        "   If a user says they would like to make a reservation, or book a table, or reserve a table, guide them by giving them this format to use To book a table, type: \"Book table under Chipo Moyo at 7PM  for 9 people at table number 9  .\" I will confirm your booking right away.'\n"    
        "   Total number of tables is 1,2,3,4,5, if any table is not available, reccomend the others. 1-3 are indoors and 4-5 are outdoors "
        "     'Use this format as is, as an example,You can copy and paste then replace with your details. To book a table, type: \"Book table under Chipo Moyo at 7PM  for 9 people at table number 9  .\" I will confirm your booking right away.'\n"
        "      'Provide a structured reply when confirming bookings in the format:\n'"
        "       'Booking confirmed for [Name] at [Time] for [Number of People] people at table number [Table Number].'"
        "   - Confirm booking details:\n"
        "     'Booking has been successfully. We look forward to serving you!'\n\n"
        "4. Sharing Menu Information\n"
        "   You retrieve menu from get_menu ()function"
        "5. Providing Support for Special Requests\n"
        "   - Handle customer queries about allergies, preferences, or special occasions:\n"
        "     'Certainly! Let me know if you have any dietary preferences or special requests, and I will assist you accordingly.'\n\n"
        "6. Resolving Unclear Messages\n"
        "   - If a message is unclear, politely ask for clarification:\n"
        "     'Apologies, quick question. Could you please clarify? For example, you can say: \"Order: item1, item2\" or "
        "\"Book table under Chipo Moyo at 7PM  for 9 people at table number 9  \"'\n\n"
        "7. Using OpenAI API for Uncommon Questions\n"
        "   - When faced with unique questions or unsupported requests, leverage the OpenAI API for intelligent responses:\n"
        "     'umm... , '\n\n"
        "8. Tone and Personality\n"
        "   - Maintain a polite, friendly, and professional tone.\n"
        "   - Express gratitude frequently to build a positive rapport:\n"
        "     'Thank you for choosing Star Restaurant. We are delighted to assist you!'\n"
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
        
        print(f"Debug: OpenAI Response -> {response}", flush=True)
        
        # Extract the first message from the assistant's reply
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
        else:
            return "Unexpected response format from the OpenAI API."

    except Exception as e:
        print(f"Error querying OpenAI API: {e}", flush=True)
        return "There was an error processing your request. Please try again later."


# Send WhatsApp message
def send_whatsapp_message(to, message):
    """
    Send a WhatsApp message using Meta's WhatsApp Business API.
    """
    try:
        meta_phone_number_id = os.getenv('META_PHONE_NUMBER_ID')  # Ensure the environment variable is set
        meta_access_token = os.getenv('META_ACCESS_TOKEN')  # Ensure the environment variable is set

        url = f"https://graph.facebook.com/v13.0/{meta_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {meta_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an error for HTTP 4xx/5xx responses
        print(f"Message sent to {to}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message to {to}: {e}")
        return None




@app.route('/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    """
    Handle GET requests for webhook verification and POST requests for incoming messages.
    """
    if request.method == 'GET':
        # Webhook verification
        verify_token = 'abc123'
        hub_mode = request.args.get('hub.mode')
        hub_token = request.args.get('hub.verify_token')
        hub_challenge = request.args.get('hub.challenge')

        print(f"Verification Request Received. Mode: {hub_mode}, Token: {hub_token}")

        if hub_mode == 'subscribe' and hub_token == verify_token:
            print("Webhook verified successfully.")
            return hub_challenge, 200
        print("Webhook verification failed.")
        return "Verification failed", 403

    elif request.method == 'POST':
        try:
            # Parse incoming JSON payload
            data = request.get_json()
            print(f"Incoming webhook data: {data}")

            # Ensure this is a WhatsApp Business Account message
            if data.get('object') == 'whatsapp_business_account':
                for entry in data.get('entry', []):
                    for change in entry.get('changes', []):
                        if change.get('field') == 'messages':
                            # Handle user messages
                            if 'messages' in change.get('value', {}):
                                messages = change['value']['messages']
                                for message in messages:
                                    from_number = message.get('from')
                                    message_body = message.get('text', {}).get('body')
                                    print(f"Message from {from_number}: {message_body}")

                                    # Process the message and generate a bot reply
                                    bot_reply = process_message(from_number, message_body)

                                    # Log the conversation
                                    log_conversation(
                                        from_number=from_number,
                                        message=message_body,
                                        bot_reply=bot_reply,
                                        status="processed"
                                    )

                                    # Send a reply back to the user
                                    send_whatsapp_message(from_number, bot_reply)

                                return jsonify({"status": "success"}), 200

                            # Handle message statuses
                            if 'statuses' in change.get('value', {}):
                                statuses = change['value']['statuses']
                                for status in statuses:
                                    print(f"Status update: {status}")
                                return jsonify({"status": "status_processed"}), 200

            return jsonify({"status": "ignored"}), 200

        except Exception as e:
            print(f"Error handling webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

        

def initialize_session():
    """
    Initialize session variables if not already present.
    """
    if 'conversation' not in session:
        session['conversation'] = []
    if 'order_flow_state' not in session:
        session['order_flow_state'] = 'start'
    if 'delivery_info' not in session:
        session['delivery_info'] = {}
    if 'last_activity' not in session:
        session['last_activity'] = datetime.now()



def check_session_inactivity(contact_number):
    """
    Check if the session has been inactive for more than 30 minutes.
    """
    if datetime.now() - session.get('last_activity', datetime.now()) > timedelta(minutes=30):
        # Save the session summary to the database before clearing the session
        session_summary = summarize_session(session['conversation'], contact_number)
        save_session_to_db(contact_number, session_summary)
        session.clear()
        print(f"Session for {contact_number} ended due to inactivity.")
        return True
    return False




def process_message(from_number, incoming_message):
    """
    Process the incoming message and return a response.
    """
    try:
        # Initialize session variables
        initialize_session()

        if check_session_inactivity(from_number):
            return "Your session has expired. Let's start fresh!"
        
        print(f"Session state before processing: {dict(session)}")

        
        session['conversation'].append({'role': 'user', 'content': incoming_message})

        incoming_message = incoming_message.lower()
        print(f"Processing message from {from_number}: {incoming_message}")
        print(f"Session state: {session}")

        # Retrieve user name and session summary
        name = get_customer_name(from_number)
        session_summary = summarize_session(session['conversation'], from_number)
        
            # Debug session state
        print(f"Debug: Current session state: {dict(session)}")

        # Handle order and delivery flow
        if "order:" in incoming_message or session.get('order_flow_state'):
            bot_reply = handle_order_and_delivery(from_number, incoming_message)
            return bot_reply
           
        # Handle ratings
        elif "rate" in incoming_message:
            bot_reply = handle_rating(from_number, incoming_message)

        # Handle order cancellations
        elif "cancel order" in incoming_message:
            bot_reply = handle_order_cancellation(from_number, incoming_message)

        # Handle table reservation cancellations
        elif "cancel reservation" in incoming_message:
            bot_reply = handle_reservation_cancellation(incoming_message)

        # Handle menu requests
        elif "menu" in incoming_message:
            bot_reply = handle_menu_request()

        # Handle table bookings
        elif "book table" in incoming_message:
            bot_reply = handle_table_booking(from_number, incoming_message)


        else:
            bot_reply = f"Hello {name}! " + query_openai_model(
                f"Context: {session_summary}\nUser: {incoming_message}"
            )

        # Append bot response to the conversation and update session timestamp
        session['conversation'].append({'role': 'assistant', 'content': bot_reply})
        session['last_activity'] = datetime.now()
        session.modified = True 

        return bot_reply

    except Exception as e:
        print(f"Error processing message: {e}")
        return "An error occurred while processing your request. Please try again later."




def handle_rating(from_number, incoming_message):
    """
    Process ratings and return a response.
    """
    try:
        match = re.search(r"rate (\d+)", incoming_message)
        if match:
            rating = int(match.group(1))
            if 1 <= rating <= 5:
                with sqlite3.connect('restaurant.db') as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT id FROM orders
                        WHERE contact_number = ? AND status = "done"
                        ORDER BY created_at DESC
                        LIMIT 1
                        ''',
                        (from_number,),
                    )
                    order = cursor.fetchone()
                    if not order:
                        return "We could not find a completed order to rate. Please ensure your order is marked as 'done' before rating."
                    cursor.execute(
                        '''
                        UPDATE orders
                        SET rating = ?
                        WHERE id = ?
                        ''',
                        (rating, order[0]),
                    )
                    conn.commit()
                    return "Thank you for your feedback! 🌟 We hope to serve you again soon."
            return "Please provide a valid rating between 1 and 5. For example, 'Rate 5'."
        return "To rate your experience, reply with 'Rate [1-5]'. For example, 'Rate 5'."
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return "Error processing your request. Please try again later."


def handle_order_cancellation(from_number, incoming_message):
    """
    Handle order cancellations and return a response.
    """
    match = re.search(r"cancel order for (.+?) with contact number (.+)", incoming_message)
    if match:
        order_details = match.group(1).strip()
        contact_number = match.group(2).strip()
        return cancel_order(contact_number, order_details)
    return (
        "Oh no 🥺, I'm sorry you want to cancel your order. "
        "Please use this format: 'Cancel order for [Order Details] with contact number [Your Contact Number]'."
    )


def handle_reservation_cancellation(incoming_message):
    """
    Handle table reservation cancellations and return a response.
    """
    match = re.search(r"cancel reservation for table (\d+)", incoming_message)
    if match:
        table_number = int(match.group(1))
        return cancel_reservation(table_number)
    return (
        "I couldn't understand which table reservation you want to cancel. "
        "Please use the format: 'Cancel reservation for table [Table Number]'."
    )


def handle_menu_request():
    """
    Retrieve and format the menu response.
    """
    menu = get_menu()
    if menu:
        reply = "Here is today's menu:\n\n"
        for category, items in menu.items():
            reply += f"*{category}:*\n" + "\n".join(items) + "\n\n"
        return reply
    return "Sorry, today's menu is not available."



def handle_table_booking(from_number, incoming_message):
    """
    Process table booking requests and return a response.
    """
    try:
        match = re.search(
            r"book table under (.+?) at ([\d:AMPamp\s]+) for (\d+) people at table (\d+)",
            incoming_message,
            re.IGNORECASE,
        )
        if match:
            name = match.group(1).strip()
            reservation_time = match.group(2).strip()
            number_of_people = int(match.group(3))
            table_number = int(match.group(4))

            # Save reservation details to the database
            save_response = save_reservation(name, from_number, reservation_time, number_of_people, table_number)
            return (
                f"Booking confirmed! 🎉\n"
                f"Name: {name}\n"
                f"Time: {reservation_time}\n"
                f"Guests: {number_of_people}\n"
                f"Table: {table_number}\n\n{save_response}"
            )
        return (
            "Please use the format: 'Book table under [Name] at [Time] for [Number] people at table [Table Number]'."
        )
    except Exception as e:
        print(f"Error in handle_table_booking: {e}")
        return "An error occurred while booking your table. Please try again later."


def handle_order_and_delivery(from_number, incoming_message):
    """
    Handle the complete flow of order placement and delivery in a single function.
    """
    try:
        # Retrieve session state
        order_flow_state = session.get('order_flow_state', 'start')
        order_details = session.get('order_details', {})

        print(f"Debug: Current order_flow_state: {order_flow_state}")
        print(f"Debug: Current order_details: {order_details}")

        # Step 1: Handle order initiation
        if order_flow_state == 'start':
            if "order:" in incoming_message:
                order_items = incoming_message.split("order:")[-1].strip()
                order_details['items'] = order_items
                session['order_flow_state'] = 'delivery_confirmation'
                session['order_details'] = order_details
                session.modified = True  # Commit session changes
                return (
                    f"Thank you! Your order for {order_items.capitalize()} has been received.\n\n"
                    f"Would you like it delivered? Reply with 'Yes' or 'No'."
                )
            return "To place an order, please use the format: 'Order: [your order details]'."

        # Step 2: Confirm delivery
        elif order_flow_state == 'delivery_confirmation':
            if incoming_message in ['yes', 'y']:
                session['order_flow_state'] = 'collect_name'
                session.modified = True
                return "Great! Let's get some details. What is your name?"
            elif incoming_message in ['no', 'n']:
                save_response = save_order(from_number, order_details['items'], delivery="No")
                session.clear()  # Reset session after completion
                return (
                    f"Thank you! Your order for {order_details['items']} is being prepared. "
                    f"It's just awaiting collection. {save_response}"
                )
            return "Please reply with 'Yes' or 'No' to confirm if you want delivery."

        # Step 3: Collect delivery name
        elif order_flow_state == 'collect_name':
            order_details['name'] = incoming_message.strip()
            session['order_flow_state'] = 'collect_location'
            session['order_details'] = order_details
            session.modified = True
            return "Got it! Please provide the delivery location."

        # Step 4: Collect delivery location
        elif order_flow_state == 'collect_location':
            order_details['location'] = incoming_message.strip()
            session['order_flow_state'] = 'collect_time'
            session['order_details'] = order_details
            session.modified = True
            return (
                "Noted! What is your preferred delivery time?\n"
                "- Type 'fastest' for immediate delivery.\n"
                "- Type 'max' for delivery within an hour.\n"
                "- Type 'custom' followed by the time (e.g., 'custom 3 hours')."
            )

        # Step 5: Collect delivery time
        elif order_flow_state == 'collect_time':
            if incoming_message.startswith('custom'):
                custom_time = incoming_message.replace('custom', '').strip()
                order_details['time'] = f"Custom - {custom_time}"
            elif incoming_message in ['fastest', 'max']:
                order_details['time'] = incoming_message.capitalize()
            else:
                return (
                    "Invalid input. Please specify:\n"
                    "- 'fastest' for immediate delivery.\n"
                    "- 'max' for delivery within an hour.\n"
                    "- 'custom' followed by the time (e.g., 'custom 3 hours')."
                )

            # Finalize order and save to database
            save_response = save_order(
                from_number,
                order_details['items'],
                delivery="Yes",
                delivery_name=order_details['name'],
                delivery_location=order_details['location'],
                delivery_time=order_details['time']
            )
            session.clear()  # Reset session after completion
            return (
                f"Thank you! Your order for {order_details['items']} will be delivered to:\n"
                f"Name: {order_details['name']}\n"
                f"Location: {order_details['location']}\n"
                f"Preferred Time: {order_details['time']}.\n\n{save_response}"
            )

        # Fallback for unexpected states
        else:
            session.clear()
            return "An unexpected error occurred. Please try placing your order again."

    except Exception as e:
        print(f"Error in handle_order_and_delivery: {e}")
        return "An error occurred while processing your order. Please try again later."


@app.route('/status-callback', methods=['POST'])
def status_callback():
    try:
        message_status = request.values.get('MessageStatus', '')
        message_sid = request.values.get('MessageSid', '')
        print(f"Message SID: {message_sid}, Status: {message_status}")
        return "Status received", 200
    except Exception as e:
        print(f"Error in status callback: {e}")
        return f"Internal Server Error: {e}", 500

def send_periodic_updates():
    try:
        with sqlite3.connect('restaurant.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT from_number, message, bot_reply FROM restaurant WHERE reported = 0')
            restaurant = cursor.fetchall()

            if restaurant:
                update_message = "Hourly Update:\n\n"
                for conv in restaurant:
                    from_number, message, bot_reply = conv
                    update_message += f"From: {from_number}\nMessage: {message}\nBot Reply: {bot_reply}\n\n"

                send_whatsapp_message(ADMIN_NUMBER, update_message)
                cursor.execute('UPDATE restaurant SET reported = 1 WHERE reported = 0')
                conn.commit()
    except Exception as e:
        print(f"Error in periodic updates: {e}")

schedule.every().hour.do(send_periodic_updates)

# Schedule the proactive messaging function
schedule.every(2).hours.do(send_intro_to_new_customers)

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
    app.run(debug=True)
