from db import get_db_connection
from whatsapp_utils import send_whatsapp_message
from config import logging, ADMIN_NUMBER
import psycopg2
import re
import json
from flask import jsonify
from datetime import datetime


# def save_reservation(name, contact_number, reservation_date, reservation_time, number_of_people, table_number):
#     """Save a reservation in the database with reservations_done set to FALSE by default."""
#     conn = get_db_connection()
#     if not conn:
#         return "Database connection failed."

#     try:
#         cursor = conn.cursor()

#         # ✅ Initialize available_tables as an empty list before using it
#         available_tables = []

#         # Check if the table is available
#         cursor.execute('SELECT is_available FROM restaurant_tables WHERE table_number = %s', (table_number,))
#         table_status = cursor.fetchone()

#         if not table_status:
#             return f"Table {table_number} does not exist in our restaurant. Please choose a valid table number."

#         if not table_status[0]:  # If the table is unavailable
#             cursor.execute('SELECT table_number, capacity FROM restaurant_tables WHERE is_available = TRUE')
#             available_tables = cursor.fetchall()

#             if not available_tables:  # ✅ Ensure available_tables is checked only after it's assigned a value
#                 return "Apologies 🥺, all tables are fully booked. Please check back later or contact us for assistance."

#             options = "\n".join([f"Table {table[0]} (Capacity: {table[1]})" for table in available_tables])
#             return f"Apologies 🥺, Table {table_number} is already booked. Please choose another table from remaining options:\n{options}\nNB* Please resend your template message with the new table number"

#         # Save the reservation with reservations_done set to FALSE
#         cursor.execute('''
#             INSERT INTO reservations (name, contact_number, reservation_time, number_of_people, table_number, reservations_done)
#             VALUES (%s, %s, %s, %s, %s, %s)
#         ''', (name, contact_number, f"{reservation_date} at {reservation_time}", number_of_people, table_number, False))

#         # Mark the table as unavailable
#         cursor.execute('UPDATE restaurant_tables SET is_available = FALSE WHERE table_number = %s', (table_number,))
#         conn.commit()

#         notification_message = (
#             f"New Reservation Alert:\n\n"
#             f"Name: {name}\n"
#             f"Contact Number: {contact_number}\n"
#             f"Time: {reservation_date} at {reservation_time}\n"
#             f"Number of People: {number_of_people}\n"
#             f"Table Number: {table_number}\n"
#             f"Status: Pending (Not yet completed)"
#         )
#         send_whatsapp_message(ADMIN_NUMBER, notification_message)

#         return f"Success! Booking confirmed for {name} on {reservation_date} at {reservation_time} for {number_of_people} people at table {table_number}."
    
#     except psycopg2.Error as e:
#         logging.error(f"Database error: {e}")
#         return "Error saving reservation."
#     finally:
#         cursor.close()
#         conn.close()

from datetime import datetime

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

            if not available_tables:
                return "Apologies 🥺, all tables are fully booked. Please check back later or contact us for assistance."

            options = "\n".join([f"Table {table[0]} (Capacity: {table[1]})" for table in available_tables])
            return (
                f"Apologies 🥺, Table {table_number} is already booked. "
                f"Please choose another table from remaining options:\n{options}\n"
                "NB* Please resend your template message with the new table number"
            )

        # ✅ Parse reservation_date + reservation_time into a valid Python datetime object
        try:
            reservation_datetime = datetime.strptime(f"{reservation_date} {reservation_time}", "%Y-%m-%d %I%p")
        except ValueError as e:
            logging.error(f"❌ Failed to parse reservation datetime: {e}")
            return "Sorry, I couldn't understand the reservation time. Please provide a valid time like '12PM' or '7PM'."

        # Save the reservation with reservations_done set to FALSE
        cursor.execute('''
            INSERT INTO reservations (name, contact_number, reservation_time, number_of_people, table_number, reservations_done)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, contact_number, reservation_datetime, number_of_people, table_number, False))

        # Mark the table as unavailable
        cursor.execute('UPDATE restaurant_tables SET is_available = FALSE WHERE table_number = %s', (table_number,))
        conn.commit()

        notification_message = (
            f"New Reservation Alert:\n\n"
            f"Name: {name}\n"
            f"Contact Number: {contact_number}\n"
            f"Time: {reservation_datetime.strftime('%Y-%m-%d %I:%M %p')}\n"
            f"Number of People: {number_of_people}\n"
            f"Table Number: {table_number}\n"
            f"Status: Pending (Not yet completed)"
        )
        send_whatsapp_message(ADMIN_NUMBER, notification_message)

        return (
            f"Success! Booking confirmed for {name} on "
            f"{reservation_datetime.strftime('%Y-%m-%d at %I:%M %p')} for "
            f"{number_of_people} people at table {table_number}."
        )

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

