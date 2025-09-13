import logging
import os
import json
from supabase import create_client, Client


SUPABASE_URL = "https://....supabase.co"
SUPABASE_KEY = "..-"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)




def get_db_connection():
    """Returns the Supabase client instance."""
    return supabase





def save_session_to_db(contact_number, session_summary):
    """
    Save or update session summary in PostgreSQL.
    """
    supabase = get_db_connection()
    if not supabase:
        logging.error("❌ Supabase client not available. Cannot save session summary.")
        return

    # Extract only the summary text if session_summary is a dictionary
    if isinstance(session_summary, dict) and "content" in session_summary:
        session_summary = session_summary["content"]

    # Ensure it’s a string before saving
    if isinstance(session_summary, list) or isinstance(session_summary, dict):
        session_summary = json.dumps(session_summary)

    try:
        # Upsert (insert or update) the session summary for the contact_number and memory_key
        data = {
            "contact_number": contact_number,
            "memory_key": "session_summary",
            "value": session_summary
        }
        response = supabase.table("user_memory").upsert(data, on_conflict=["contact_number", "memory_key"]).execute()
        if response.get("status_code", 200) >= 400:
            logging.error(f"❌ Supabase error while saving session summary: {response}")
        else:
            logging.info(f"✅ Session summary saved for {contact_number}")
    except Exception as e:
        logging.error(f"❌ Error while saving session summary to Supabase: {e}")



# Log new conversation or updates in the database
def log_conversation(from_number, message, bot_reply, status):
    """
    Log customer conversations in the database.
    """
    supabase = get_db_connection()
    if not supabase:
        logging.info("❌ Supabase client not available. Cannot log conversation.")
        return

    try:
        logging.info(f"📝 Logging conversation: {from_number} - {message} - {bot_reply} - {status}")
        data = {
            "from_number": from_number,
            "message": message,
            "bot_reply": bot_reply,
            "status": status,
            "reported": 0
        }
        response = supabase.table("restaurant").insert(data).execute()
        if response.get("status_code", 200) >= 400:
            logging.warning(f"❌ Supabase error while logging conversation: {response}")
        else:
            logging.info("✅ Conversation logged successfully.")
    except Exception as e:
        logging.warning(f"Error while logging conversation to Supabase: {e}")



# def store_user_query(phone_number, query):
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     try:
#         cursor.execute("""
#             INSERT INTO user_queries (phone_number, last_query, created_at)
#             VALUES (%s, %s, NOW())
#             ON CONFLICT (phone_number)
#             DO UPDATE SET 
#                 last_query = EXCLUDED.last_query,
#                 created_at = NOW()
#         """, (phone_number, query))
#         conn.commit()
#     finally:
#         cursor.close()
#         conn.close()


# def get_user_last_query(phone_number):
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     try:
#         cursor.execute("""
#             SELECT last_query FROM user_queries 
#             WHERE phone_number = %s
#         """, (phone_number,))
#         result = cursor.fetchone()
#         return result[0] if result else None
#     finally:
#         cursor.close()
#         conn.close()
