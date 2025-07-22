
from db import get_db_connection
from whatsapp_utils import send_whatsapp_message
import logging
import psycopg2
from config import ADMIN_NUMBER, logging




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


