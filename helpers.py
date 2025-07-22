from config import logging
from db import get_db_connection
import psycopg2
import re
import datetime
from datetime import timedelta, datetime
from db import save_session_to_db

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




def is_valid_phone_number(phone_number): 
    """ Validate international phone numbers (E.164 format). """
    pattern = re.compile(r"^\+[1-9]\d{6,14}$")  # Correct E.164 format
    return bool(pattern.match(phone_number))


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




def check_inactivity(from_number):
    from openai_handling import summarize_session
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



