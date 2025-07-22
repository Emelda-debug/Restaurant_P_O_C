from config import logging
import re
import psycopg2
from flask import jsonify
from db import get_db_connection
from whatsapp_utils import send_whatsapp_message

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


