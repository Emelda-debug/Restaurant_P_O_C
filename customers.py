from db import get_db_connection
from config import logging
import psycopg2
from whatsapp_utils import send_template_message
from helpers import is_valid_phone_number
import time


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

