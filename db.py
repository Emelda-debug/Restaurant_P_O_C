import psycopg2
import logging
import os
import json

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
