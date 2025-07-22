from db import get_db_connection
import psycopg2
from config import logging
from whatsapp_utils import send_whatsapp_message, send_whatsapp_image, send_whatsapp_interactive
from flask import session
import os

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


from image_grid_generator import generate_menu_grid_image
def send_food_image(query, phone_number):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 🥇 Try exact item name match
    cursor.execute("""
        SELECT item_name, price, image_url 
        FROM menu 
        WHERE LOWER(item_name) = %s
    """, (query.lower(),))
    item = cursor.fetchone()

    if item:
        name, price, image_url = item
        message = f"*{name}* — ${price:.2f}."
        send_whatsapp_image(phone_number, image_url, message)  # still a URL
        return {"status": "item image sent"}

    # 🥈 Try category match (returns multiple)
    cursor.execute("""
        SELECT item_name, price, image_url 
        FROM menu 
        WHERE LOWER(category) = %s
    """, (query.lower(),))
    items = cursor.fetchall()

    if items:
        # Generate image grid
        grid_path = generate_menu_grid_image(items)
        for path in grid_path:
            send_whatsapp_image(phone_number, path)

        message = f"Our Delectable *{query}* options:"
        send_whatsapp_message(phone_number, message)

        return {"status": "category grid sent"}

    return {"status": "no match found"}


import difflib
from image_grid_generator import generate_menu_grid_image
def send_food_image(query, phone_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    query_lower = query.lower()

    # --- 🥇 First check if it's a category ---
    known_categories = ['breakfast', 'lunch', 'dinner', 'beverages', 'dessert', 'snacks', 'alcoholic', 'non-alcoholic']
    if query_lower in known_categories:
        cursor.execute("""
            SELECT item_name, price, image_url 
            FROM menu 
            WHERE LOWER(category) = %s
        """, (query_lower,))
        category_items = cursor.fetchall()

        if category_items:
            grid_paths = generate_menu_grid_image(category_items)
            for path in grid_paths:
                send_whatsapp_image(phone_number, path)

            message = f"Our Delectable *{query}* options:"
            send_whatsapp_message(phone_number, message)
            return {"status": "category grid sent"}

    # --- 🥈 Otherwise, try partial/fuzzy item name matching ---
    cursor.execute("SELECT item_name, price, image_url FROM menu")
    all_items = cursor.fetchall()
    matched_items = []

    for item_name, price, image_url in all_items:
        if query_lower in item_name.lower() or item_name.lower() in query_lower:
            matched_items.append((item_name, price, image_url))
        else:
            words = item_name.lower().split()
            if any(word in query_lower for word in words):
                matched_items.append((item_name, price, image_url))

    if matched_items:
        if len(matched_items) == 1:
            name, price, image_url = matched_items[0]
            message = f"*{name}* — ${price:.2f}."
            send_whatsapp_image(phone_number, image_url, message)
            return {"status": "item image sent"}
        else:
            grid_paths = generate_menu_grid_image(matched_items)
            for path in grid_paths:
                send_whatsapp_image(phone_number, path)

            message = f"Our tasty *{query}* options:"
            send_whatsapp_message(phone_number, message)
            return {"status": "fuzzy matched grid sent"}

    return {"status": "no match found"}





# def send_menu_page(items, phone_number, query, page_number=1):
#     """Separate function to handle menu pagination"""
#     try:
#         # Generate image grid
#         grid_path, total_pages = generate_menu_grid_image(items, page_number=page_number)
        
#         if not grid_path:
#             return {"status": "error generating grid"}
        
#         # Send image using file path
#         send_whatsapp_image(phone_number, grid_path)
        
#         message = f"Here are our *{query}* options:"
#         send_whatsapp_message(phone_number, message)
        
#         # Add pagination buttons if needed
#         if page_number < total_pages:
#             send_whatsapp_interactive(
#                 phone_number,
#                 body_text=f"Page {page_number} of {total_pages}. Want to see more?",
#                 button_id=f"next_page_{page_number+1}",
#                 button_title="Next Page"
#             )
        
#         # Clean up the temporary file
#         try:
#             os.remove(grid_path)
#         except:
#             pass  # Ignore cleanup errors
        
#         return {"status": "category grid sent"}
    
#     except Exception as e:
#         print(f"Error sending menu page: {e}")
#         return {"status": "error"}