import traceback
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Blueprint
from menu import send_food_image
import psycopg2
import supabase
from flask_bcrypt import Bcrypt
from supabase_handling import check_bucket_exists
from whatsapp_utils import send_whatsapp_message, trigger_whatsapp_flow
from customers import get_customer_name
import pandas as pd
import os
import logging
from dotenv import load_dotenv
import requests
from config import bcrypt
from db import get_db_connection


# Load environment variables from .env file
load_dotenv()

# Configure Logging
logging.basicConfig(
    filename="app.log",  
    level=logging.DEBUG,  
    format="%(asctime)s - %(levelname)s - %(message)s"
)




dash_blueprint = Blueprint('dash', __name__)
 





def notify_user(contact_number, message):
    """
    Send a WhatsApp notification to the user.
    """
    try:
        # Remove 'whatsapp:' prefix if already present
        if contact_number.startswith('whatsapp:'):
            contact_number = contact_number.replace('whatsapp:', '')

        # Send the WhatsApp message
        send_whatsapp_message(contact_number, message)  # Pass only `to` and `message`
        logging.info(f"Notification sent to {contact_number}: {message}")
    except Exception as e:
        logging.error(f"Error sending notification to {contact_number}: {e}")






def verify_password(username, password):
    logging.info(f"Debug: Verifying password for user: {username}")

    supabase = get_db_connection()
    if not supabase:
        logging.debug("Debug: Supabase client is None, returning False")
        return False


    try:
        response = supabase.table("admin_users") \
            .select("password_hash") \
            .eq("username", username) \
            .single() \
            .execute()

        # Only check the data attribute
        user = response.data
        if not user or "password_hash" not in user:
            logging.debug("Debug: No user found or missing password hash")
            return False

        if bcrypt.check_password_hash(user["password_hash"], password):
            logging.info("Debug: Password verification successful")
            return True
        else:
            logging.debug("Debug: Password verification failed")
            return False

    except Exception as e:
        logging.debug(f"Debug: Exception while verifying password: {e}")
        if 'response' in locals():
            logging.debug(f"Debug: Response type: {type(response)}, attributes: {dir(response)}")
        return False


@dash_blueprint.route('/', methods=['GET', 'POST'])
def login():
    """
    Login route to authenticate users.
    """
    logging.info("Debug: Login route accessed")

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        logging.debug(f"Debug: Received login request for username: {username}")

        if verify_password(username, password):
            logging.debug("Debug: Authentication successful, setting session and redirecting")
            session['user'] = username
            # Fetch and log user role
            try:
                supabase = get_db_connection()
                if supabase:
                    resp = supabase.table("admin_users").select("role").eq("username", username).single().execute()
                    user_role = resp.data["role"] if hasattr(resp, "data") and resp.data and "role" in resp.data else None
                    logging.info(f"Debug: User '{username}' logged in with role: '{user_role}'")
                else:
                    logging.warning("Debug: Could not fetch user role, Supabase connection failed.")
            except Exception as e:
                logging.error(f"Debug: Exception while fetching user role for '{username}': {e}")
            return redirect(url_for('dash.dashboard'))
        else:
            logging.error("Authentication failed, rendering login page with error")
            return render_template('index.html', error="Invalid username or password")

    logging.debug("Debug: Rendering login page")
    return render_template('index.html')



@dash_blueprint.route('/dashboard')
def dashboard():
    """
    Fetch key metrics for the restaurant dashboard using Supabase.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return render_template("d.html", error="Database connection failed")

    user_profile_image = None
    monthly_orders = []
    total_orders = 0
    completed_orders = 0
    pending_orders = 0
    total_reservations = 0
    available_tables = 0
    total_customers = 0
    total_menu_items = 0
    ratings_data = []
    top_menu_items = []
    try:
        # Get user's profile image
        profile_resp = supabase.table("admin_users").select("profile_image").eq("username", session['user']).single().execute()
        if getattr(profile_resp, "data", None) and profile_resp.data.get("profile_image"):
            user_profile_image = profile_resp.data["profile_image"]

        # Total orders
        total_orders = supabase.table("orders").select("id", count="exact").execute().count or 0
        # Completed orders
        completed_orders = supabase.table("orders").select("id", count="exact").eq("status", "done").execute().count or 0
        # Pending orders
        pending_orders = supabase.table("orders").select("id", count="exact").not_.in_("status", ["done", "cancelled"]).execute().count or 0
        # Total reservations
        total_reservations = supabase.table("reservations").select("id", count="exact").execute().count or 0
        # Available tables
        available_tables = supabase.table("restaurant_tables").select("table_number", count="exact").eq("is_available", True).execute().count or 0
        # Total customers
        total_customers = supabase.table("customers").select("id", count="exact").execute().count or 0
        # Total menu items
        total_menu_items = supabase.table("menu").select("id", count="exact").eq("available", True).execute().count or 0

        # Ratings data (group by rating)
        ratings_resp = supabase.rpc("get_ratings_count_by_value").execute()  # You may need to create a Postgres function for this
        ratings_data = ratings_resp.data if hasattr(ratings_resp, "data") else []

        # Monthly orders (group by month)
        monthly_orders_resp = supabase.rpc("get_monthly_orders").execute()  # You may need to create a Postgres function for this
        monthly_orders = monthly_orders_resp.data if hasattr(monthly_orders_resp, "data") and monthly_orders_resp.data is not None else []

        # Top menu items
        top_menu_resp = supabase.rpc("get_top_menu_items").execute()  # You may need to create a Postgres function for this
        top_menu_items = top_menu_resp.data if hasattr(top_menu_resp, "data") else []

        return render_template("d.html",
            total_orders=total_orders,
            completed_orders=completed_orders,
            pending_orders=pending_orders,
            total_reservations=total_reservations,
            available_tables=available_tables,
            total_contacts=total_customers,
            total_menu_items=total_menu_items,
            ratings_data=ratings_data,
            top_menu_items=top_menu_items,
            monthly_orders=monthly_orders,
            user_profile_image=user_profile_image,
            username=session['user']
        )
    except Exception as e:
        logging.error(f"❌ Supabase error: {e}")
        return render_template("d.html",
            error="Error fetching dashboard data",
            total_orders=total_orders,
            completed_orders=completed_orders,
            pending_orders=pending_orders,
            total_reservations=total_reservations,
            available_tables=available_tables,
            total_contacts=total_customers,
            total_menu_items=total_menu_items,
            ratings_data=ratings_data,
            top_menu_items=top_menu_items,
            monthly_orders=monthly_orders,
            user_profile_image=user_profile_image,
            username=session.get('user', None)
        )




@dash_blueprint.route('/menus', methods=['GET', 'POST'])
def menus():
    """
    Manage menus (view, add, bulk upload via Excel).
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    menus = []
    try:
        if request.method == 'POST':
            file = request.files.get('file')

            if file and file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(file, engine='openpyxl')
                    required_columns = {'Category', 'Item Name', 'Price', 'Available'}
                    if required_columns.issubset(df.columns):
                        rows_to_insert = []
                        for _, row in df.iterrows():
                            if pd.isna(row['Category']) or pd.isna(row['Item Name']) or pd.isna(row['Price']) or pd.isna(row['Available']):
                                logging.info(f"Skipping row due to missing data: {row}")
                                continue  # Skip this row
                            category = row['Category']
                            item_name = row['Item Name']
                            price = row['Price']
                            available = bool(row['Available'])
                            rows_to_insert.append({
                                "category": category,
                                "item_name": item_name,
                                "price": price,
                                "available": available
                            })
                        if rows_to_insert:
                            supabase.table("menu").upsert(rows_to_insert, on_conflict=["item_name"]).execute()
                    else:
                        logging.error("Error: Missing required columns (Category, Item Name, Price, Available)")
                except Exception as e:
                    logging.error(f"Error processing Excel file: {e}")

            elif 'category' in request.form and 'item_name' in request.form:
                category = request.form['category']
                item_name = request.form['item_name']
                price = request.form['price']
                available = bool(request.form['available'])
                image_file = request.files.get('image')
                image_url = None

                if image_file and image_file.filename != '':
                    try:
                        from supabase_handling import upload_image_to_supabase, list_buckets, check_bucket_exists
                        list_buckets()
                        check_bucket_exists("leya-menu-items")
                        image_url = upload_image_to_supabase(image_file)
                    except Exception as e:
                        logging.error(f"Main app upload error: {str(e)}")
                        logging.error(f"Full traceback: {traceback.format_exc()}")

                row = {
                    "category": category,
                    "item_name": item_name,
                    "price": price,
                    "available": available
                }
                if image_url:
                    row["image_url"] = image_url
                try:
                    supabase.table("menu").upsert([row], on_conflict=["item_name"]).execute()
                except Exception as e:
                    logging.error(f"Error inserting menu item: {e}")

        # Fetch all menu items
        resp = supabase.table("menu").select("*").execute()
        menus = resp.data if hasattr(resp, "data") and resp.data else []
    except Exception as e:
        logging.error(f"Supabase error while fetching menu items: {e}")
        menus = []

    return render_template('menus.html', menus=menus)




@dash_blueprint.route('/edit_menu/<int:menu_id>', methods=['POST'])
def edit_menu(menu_id):
    """
    Edit a menu item.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    # Get form data
    category = request.form.get('category')
    item_name = request.form.get('item_name')
    price = request.form.get('price')
    available = bool(int(request.form.get('available', 1)))
    image_file = request.files.get('image')
    image_url = None

    # If a new image is uploaded, handle upload
    if image_file and image_file.filename != '':
        try:
            from supabase_handling import upload_image_to_supabase, list_buckets, check_bucket_exists
            list_buckets()
            check_bucket_exists("taguta-menu-items")
            image_url = upload_image_to_supabase(image_file)
        except Exception as e:
            logging.error(f"Edit menu upload error: {str(e)}")
            logging.error(f"Full traceback: {traceback.format_exc()}")

    # Build the update data
    update_data = {
        "category": category,
        "item_name": item_name,
        "price": price,
        "available": available
    }
    if image_url:
        update_data["image_url"] = image_url

    try:
        supabase.table("menu").update(update_data).eq("id", menu_id).execute()
    except Exception as e:
        logging.error(f"Supabase error while editing menu item: {e}")

    return redirect(url_for('dash.menus'))


@dash_blueprint.route('/conversations', methods=['GET'])
def conversations():
    """
    Fetch and display all user-bot conversations, ensuring names are correctly fetched.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    # Get filter parameters
    phone_filter = request.args.get('phone_filter', '').strip()
    name_filter = request.args.get('name_filter', '').strip().lower()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    try:
        # Build Supabase query
        query = supabase.table("restaurant").select("from_number, message, bot_reply, timestamp")
        if phone_filter:
            query = query.ilike("from_number", f"%{phone_filter}%")
        if start_date and end_date:
            query = query.gte("timestamp", start_date).lte("timestamp", end_date)
        query = query.order("from_number", desc=False).order("timestamp", desc=False)
        resp = query.execute()
        raw_messages = resp.data if hasattr(resp, "data") and resp.data else []

        transcripts = {}
        for msg in raw_messages:
            phone_number = msg.get("from_number")
            customer_name = get_customer_name(phone_number)  # Fetch name using function
            # Apply name filter in Python instead of SQL
            if name_filter and name_filter not in customer_name.lower():
                continue  # Skip this conversation if name does not match
            if phone_number not in transcripts:
                transcripts[phone_number] = {"name": customer_name, "messages": []}
            transcripts[phone_number]["messages"].append({
                "message": msg.get("message"),
                "bot_reply": msg.get("bot_reply"),
                "timestamp": msg.get("timestamp")
            })
    except Exception as e:
        logging.error(f"Supabase error while fetching conversations: {e}")
        transcripts = {}

    return render_template('conversations.html', transcripts=transcripts, phone_filter=phone_filter, name_filter=name_filter, start_date=start_date, end_date=end_date)


@dash_blueprint.route('/menus/delete/<int:menu_id>', methods=['POST'])
def delete_menu_item(menu_id):
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        supabase.table("menu").delete().eq("id", menu_id).execute()
    except Exception as e:
        logging.error(f"Supabase error while deleting menu item: {e}")
        return "An error occurred while deleting the menu item.", 500

    return redirect(url_for('dash.menus'))


@dash_blueprint.route('/set_highlight/<int:menu_id>', methods=['POST'])
def set_highlight(menu_id):
    """
    Set a menu item as the highlight of the day.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        # Reset all highlights
        supabase.table("menu").update({"highlight": False}).gte("id", 0).execute()

        # Set the selected item as the highlight
        supabase.table("menu").update({"highlight": True}).eq("id", menu_id).execute()
    except Exception as e:
        logging.error(f"Supabase error while setting highlight: {e}")
        return "There was an issue setting the highlight. Please try again later."

    return redirect(url_for('dash.menus'))


@dash_blueprint.route('/reservations')
def reservations():
    """
    View all active reservations.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        resp = supabase.table("reservations") \
            .select("*") \
            .eq("reservations_done", False) \
            .execute()
        reservations = resp.data if hasattr(resp, "data") and resp.data else []
    except Exception as e:
        logging.error(f"Supabase error while fetching reservations: {e}")
        reservations = []

    return render_template('reservations.html', reservations=reservations)




@dash_blueprint.route('/free-table/<int:reservation_id>', methods=['POST'])
def free_table(reservation_id):
    """
    Free up a table after a reservation is completed.
    """
    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        # Get table number and contact number from the reservation
        reservation_resp = supabase.table("reservations") \
            .select("table_number, contact_number") \
            .eq("id", reservation_id) \
            .single() \
            .execute()
        reservation = reservation_resp.data if hasattr(reservation_resp, "data") else None
        if not reservation:
            return "Reservation not found.", 404
        table_number = reservation.get("table_number")
        contact_number = reservation.get("contact_number")

        # Update the table's availability
        supabase.table("restaurant_tables") \
            .update({"is_available": True}) \
            .eq("table_number", table_number) \
            .execute()

        # Mark reservation as done
        supabase.table("reservations") \
            .update({"reservations_done": True}) \
            .eq("id", reservation_id) \
            .execute()

        # 📩 Send Notification to Customer
        message = (
            f"Your reservation for table {table_number} has now ended. "
            "We hope you had a great experience at Star Restaurant! 🌟\n\n"
            "We value your feedback! Please rate your experience from 1 (Poor) to 5 (Excellent):"
            "If you are using whatsapp on a device that does not support forms:\n"
            "Reply with 'R Rate [1-5]' e.g. R Rate 4.\n"
            "Else, use the form to rate your experience"
        )
        flow_cta = "Rate Your Reservation Experience"
        flow_name = "reservation_rating"

        flow_response = trigger_whatsapp_flow(contact_number, message, flow_cta, flow_name)
        logging.debug(f"🔍 Flow Trigger Debug - User: {contact_number}, Response: {flow_response}")

    except Exception as e:
        logging.error(f"Supabase error: {e}")
        return "Error freeing table.", 500

    return redirect(url_for('reservations'))



@dash_blueprint.route('/orders')
def orders():
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        response = supabase.table("orders") \
            .select("*") \
            .in__("status", ["received", "in-transit"]) \
            .execute
        orders = response.data if hasattr(response, "data") else []
    except Exception as e:
        logging.error(f"Supabase error while fetching orders: {e}")
        orders = []
    return render_template('orders.html', orders=orders)



@dash_blueprint.route('/orders/done/<int:order_id>', methods=['POST'])
def mark_order_done(order_id):
    flow_id = 1146774760431392
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        response = supabase.table("orders") \
            .select("* ")\
            .eq("id", order_id) \
            .single() \
            .execute() \
            
        order = response.data if hasattr(response, "data") else None
        if not order:
            return "Order not found.", 404 
        contact_number = order.get("contact_number")
        order_details = order.get("order_details")
        status = order.get("status")
        if status == "done":
            return redirect(url_for('dash.orders'))  # Already done, no action needed
        message = (
            f"Your order for '{order_details}' has been marked as done. "
            "Thank you for choosing Leya Restaurant! 🌟\n\n"
            "We value your feedback! Please rate your experience below."
        )
        flow_cta = "Rate Your Ordering Experience"
        flow_name = "order_rating"
        flow_response = trigger_whatsapp_flow(contact_number, message, flow_cta, flow_name)
        logging.debug(f"🔍 Flow Trigger Debug - User: {contact_number}, Response: {flow_response}")
    except Exception as e:
        logging.error(f"Supabase error while fetching order: {e}")
        return "Error marking the order as done.", 500

    return redirect(url_for('orders'))


@dash_blueprint.route('/ratings')
def ratings():
    """
    View all ratings for completed orders and reservations.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        # Fetch ratings for orders
        order_resp = supabase.table("orders") \
            .select("id, contact_number, order_details, rating") \
            .not_.is_("rating", None) \
            .execute()
        order_ratings = []
        if hasattr(order_resp, "data") and order_resp.data:
            for row in order_resp.data:
                order_ratings.append({
                    "id": row.get("id"),
                    "contact_number": row.get("contact_number"),
                    "details": row.get("order_details"),
                    "rating": row.get("rating"),
                    "type": "Order"
                })

        # Fetch ratings for reservations
        reservation_resp = supabase.table("reservations") \
            .select("id, contact_number, name, rating") \
            .not_.is_("rating", None) \
            .execute()
        reservation_ratings = []
        if hasattr(reservation_resp, "data") and reservation_resp.data:
            for row in reservation_resp.data:
                reservation_ratings.append({
                    "id": row.get("id"),
                    "contact_number": row.get("contact_number"),
                    "details": row.get("name"),
                    "rating": row.get("rating"),
                    "type": "Reservation"
                })

        # Combine both lists into one
        ratings = order_ratings + reservation_ratings

    except Exception as e:
        logging.error(f"Supabase error while fetching ratings: {e}")
        ratings = []

    return render_template('ratings.html', ratings=ratings)




@dash_blueprint.route('/orders/in-transit/<int:order_id>', methods=['POST'])
def mark_order_in_transit(order_id):
    """
    Mark an order as 'in-transit'.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))
    
    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        # Update the order status to 'in-transit'
        update_resp = supabase.table("orders") \
            .update({"status": "in-transit"}) \
            .eq("id", order_id) \
            .execute()

        # Retrieve contact number and order details
        order_resp = supabase.table("orders") \
            .select("contact_number, order_details") \
            .eq("id", order_id) \
            .single() \
            .execute()
        order = order_resp.data if hasattr(order_resp, "data") else None
        if order:
            contact_number = order.get("contact_number")
            order_details = order.get("order_details")
            message = f"Your order for '{order_details}' is now in transit. Expect it shortly!"
            notify_user(contact_number, message)

    except Exception as e:
        logging.error(f"Supabase error while updating order: {e}")
        return "Error marking the order as in-transit.", 500

    return redirect(url_for('orders'))



@dash_blueprint.route('/contacts', methods=['GET', 'POST'])
def contacts():
    """
    Manage contacts (view, add, bulk upload via Excel).
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        if request.method == 'POST':
            file = request.files.get('file')

            if file and file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(file, engine='openpyxl')
                    if {'Name', 'Contact Number'}.issubset(df.columns):
                        rows_to_insert = []
                        for _, row in df.iterrows():
                            name = row['Name']
                            contact_number = row['Contact Number']
                            status = 'new'
                            if pd.isna(name) or pd.isna(contact_number):
                                continue
                            rows_to_insert.append({
                                "name": name,
                                "contact_number": contact_number,
                                "status": status
                            })
                        if rows_to_insert:
                            supabase.table("customers").upsert(rows_to_insert, on_conflict=["contact_number"]).execute()
                    else:
                        logging.error("Error: Missing required columns (Name, Contact Number)")
                except Exception as e:
                    logging.error(f"Error processing Excel file: {e}")

            elif 'name' in request.form and 'contact_number' in request.form:
                name = request.form['name']
                contact_number = request.form['contact_number']
                status = 'new'
                try:
                    supabase.table("customers").upsert([
                        {"name": name, "contact_number": contact_number, "status": status}
                    ], on_conflict=["contact_number"]).execute()
                except Exception as e:
                    logging.error(f"Error inserting contact: {e}")

        # Fetch all contacts
        resp = supabase.table("customers").select("name, contact_number, status").execute()
        contacts = resp.data if hasattr(resp, "data") and resp.data else []

    except Exception as e:
        logging.error(f"Supabase error while fetching contacts: {e}")
        contacts = []

    return render_template('contacts.html', contacts=contacts)



@dash_blueprint.route('/logout')
def logout():
    """
    Log out the user and clear the session.
    """
    session.clear()
    return redirect(url_for('dash.login'))


@dash_blueprint.route('/contacts/delete/<contact_number>', methods=['POST'])
def delete_contact(contact_number):
    """
    Delete a contact by its contact number using Supabase.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        resp = supabase.table("customers").delete().eq("contact_number", contact_number).execute()
        logging.debug(f"Debug: Supabase delete response for contact_number={contact_number}: {resp}")
    except Exception as e:
        logging.error(f"Supabase error while deleting contact: {e}")
        return "Error deleting the contact.", 500

    return redirect(url_for('contacts'))


# @dash_blueprint.route('/conversation/<phone>')
# def get_conversation(phone):
#     """
#     Fetch conversation data for a specific phone number (for AJAX modal display).
#     """
#     if 'user' not in session:
#         return jsonify({'error': 'Unauthorized'}), 401

#     conn = get_db_connection()
#     if not conn:
#         return jsonify({'error': 'Database connection failed'}), 500

#     try:
#         cursor = conn.cursor()
        
#         # Fetch messages for the specific phone number
#         cursor.execute("""
#             SELECT message, bot_reply, timestamp 
#             FROM restaurant 
#             WHERE from_number = %s 
#             ORDER BY timestamp ASC
#         """, (phone,))
        
#         raw_messages = cursor.fetchall()
        
#         # Format messages for JSON response
#         messages = []
#         for msg in raw_messages:
#             messages.append({
#                 "message": msg[0],
#                 "bot_reply": msg[1],
#                 "timestamp": str(msg[2])  # Convert timestamp to string for JSON
#             })
        
#         # Get customer name
#         customer_name = get_customer_name(phone)
        
#         return jsonify({
#             "name": customer_name,
#             "phone": phone,
#             "messages": messages
#         })

#     except psycopg2.Error as e:
#         logging.error(f"Database error while fetching conversation for {phone}: {e}")
#         return jsonify({'error': 'Database error'}), 500

#     finally:
#         cursor.close()
#         conn.close()


@dash_blueprint.route('/chat/<phone>')
def chat_view(phone):
    """
    Display individual chat conversation with bubble interface using Supabase.
    """
    if 'user' not in session:
        return redirect(url_for('login'))

    supabase = get_db_connection()
    if not supabase:
        return "Database connection failed", 500

    try:
        resp = supabase.table("restaurant").select("message, bot_reply, timestamp").eq("from_number", phone).order("timestamp", desc=False).execute()
        logging.debug(f"Debug: Supabase chat fetch response for phone={phone}: {resp}")
        raw_messages = resp.data if hasattr(resp, "data") and resp.data else []

        # Format messages for template
        messages = []
        for msg in raw_messages:
            messages.append({
                "message": msg.get("message"),
                "bot_reply": msg.get("bot_reply"),
                "timestamp": msg.get("timestamp")
            })

        # Get customer name
        customer_name = get_customer_name(phone)

        return render_template('chat.html', 
                             messages=messages, 
                             customer_name=customer_name, 
                             phone_number=phone)

    except Exception as e:
        logging.error(f"Supabase error while fetching chat for {phone}: {e}")
        return "Database error", 500


@dash_blueprint.route('/profile', methods=['GET', 'POST'])
def profile():
    """
    User profile page for changing password and avatar.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    success_message = None
    error_message = None
    user_profile_image = None

    supabase = get_db_connection()
    if not supabase:
        error_message = "Database connection failed"
        return render_template('profile.html', success_message=success_message, error_message=error_message, user_profile_image=user_profile_image)

    # Get current user's profile image
    try:
        resp = supabase.table("admin_users").select("profile_image").eq("username", session['user']).single().execute()
        if hasattr(resp, "data") and resp.data and resp.data.get("profile_image"):
            user_profile_image = resp.data["profile_image"]
    except Exception as e:
        logging.error(f"Error fetching profile image: {e}")

    if request.method == 'POST':
        try:
            # Handle password change
            if 'change_password' in request.form:
                current_password = request.form['current_password']
                new_password = request.form['new_password']
                confirm_password = request.form['confirm_password']

                # Verify current password
                if not verify_password(session['user'], current_password):
                    error_message = "Current password is incorrect"
                elif new_password != confirm_password:
                    error_message = "New passwords do not match"
                elif len(new_password) < 6:
                    error_message = "New password must be at least 6 characters long"
                else:
                    # Update password
                    new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
                    try:
                        supabase.table("admin_users").update({"password_hash": new_password_hash}).eq("username", session['user']).execute()
                        success_message = "Password updated successfully"
                    except Exception as e:
                        logging.error(f"Error updating password: {e}")
                        error_message = "An error occurred while updating your password"

            # Handle profile picture update
            elif 'update_profile' in request.form:
                profile_image = request.files.get('profile_image')
                if profile_image and profile_image.filename:
                    import os
                    upload_dir = os.path.join('static', 'uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    filename = f"profile_{session['user']}.{profile_image.filename.split('.')[-1]}"
                    filepath = os.path.join(upload_dir, filename)
                    profile_image.save(filepath)
                    try:
                        supabase.table("admin_users").update({"profile_image": f"uploads/{filename}"}).eq("username", session['user']).execute()
                        success_message = "Profile picture updated successfully"
                        user_profile_image = f"uploads/{filename}"
                    except Exception as e:
                        logging.error(f"Error updating profile image: {e}")
                        error_message = "An error occurred while updating your profile image"
                else:
                    error_message = "Please select a valid image file"
        except Exception as e:
            logging.error(f"Error updating profile: {e}")
            error_message = "An error occurred while updating your profile"

    return render_template('profile.html', 
                         success_message=success_message, 
                         error_message=error_message,
                         user_profile_image=user_profile_image)


@dash_blueprint.route('/add_user', methods=['GET', 'POST'])
def add_user():
    """
    Add user page - only accessible by admin.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))
    
    # Check if current user is admin using Supabase
    supabase = get_db_connection()
    if not supabase:
        return redirect(url_for('dash.dashboard'))

    user_role = None
    user_profile_image = None
    success_message = None
    error_message = None
    users = []

    try:
        resp = supabase.table("admin_users").select("role, profile_image").eq("username", session['user']).single().execute()
        logging.debug(f"Debug: Supabase response for user role: {resp}")
        result = resp.data if hasattr(resp, "data") and resp.data else None
        logging.debug(f"Debug: Result from Supabase: {result}")
        user_role = result["role"] if result and "role" in result else 'user'
        user_profile_image = result["profile_image"] if result and "profile_image" in result else None
        logging.debug(f"Debug: user_role value: '{user_role}' (type: {type(user_role)}) for user: {session.get('user')}")
        if not (isinstance(user_role, str) and user_role.strip().lower() == 'admin'):
            logging.warning(f"Debug: Access denied for user '{session.get('user')}', user_role='{user_role}' (checked as '{user_role.strip().lower() if isinstance(user_role, str) else user_role}')")
            return redirect(url_for('dash.forbidden', user_role=user_role))
    except Exception as e:
        logging.error(f"Error checking user role: {e}")
        return redirect(url_for('dash.forbidden', user_role='user'))

    if request.method == 'POST':
        username = request.form.get('username')
        role = request.form.get('role', 'user')
        if not username:
            error_message = "Username is required"
        else:
            try:
                # Check if username already exists (do not use .single())
                resp = supabase.table("admin_users").select("username").eq("username", username).execute()
                logging.debug(f"Debug: Supabase response for username existence check: {resp}")
                if hasattr(resp, "data") and resp.data:
                    error_message = "Username already exists"
                else:
                    # Hash the default password
                    default_password = "taguta"
                    password_hash = bcrypt.generate_password_hash(default_password).decode('utf-8')
                    user_data = {
                        "username": username,
                        "password_hash": password_hash,
                        "role": role
                    }
                    logging.debug(f"Debug: Attempting to insert user: {user_data}")
                    try:
                        insert_resp = supabase.table("admin_users").insert(user_data).execute()
                        logging.debug(f"Debug: Supabase insert response: {insert_resp}")
                        success_message = f"User '{username}' created successfully with default password 'taguta'"
                    except Exception as insert_e:
                        logging.error(f"Error during Supabase insert: {insert_e}")
                        error_message = f"An error occurred while creating the user: {insert_e}"
            except Exception as e:
                logging.error(f"Error creating user: {e}")
                error_message = f"An error occurred while creating the user: {e}"

    # Fetch all users to display
    try:
        resp = supabase.table("admin_users").select("username, role, created_at").order("created_at", desc=True).execute()
        users = resp.data if hasattr(resp, "data") and resp.data else []
    except Exception as e:
        logging.error(f"Error fetching users: {e}")
        users = []

    return render_template('add_user.html', 
                         success_message=success_message, 
                         error_message=error_message,
                         users=users,
                         user_profile_image=user_profile_image)  

@dash_blueprint.route('/forbidden')
def forbidden():
    """
    Forbidden access page for non-admin users.
    """
    user_role = request.args.get('user_role', 'user')
    return render_template('forbidden.html', user_role=user_role)



@dash_blueprint.errorhandler(404)
def dash_not_found_error(error):
    """
    Handle 404 errors within the dash blueprint.
    """
    return render_template('404.html'), 404

@dash_blueprint.route('/test-food-image')
def test_food_image():
    """Test single item image sending"""
    result = send_food_image(query="Pancakes", phone_number="+263773344079")
    return f"✅ Test result: {result}"

@dash_blueprint.route('/test-grid-image')
def test_grid_image():
    """Test category grid image sending"""
    # This should trigger the category search within send_food_image
    result = send_food_image(query="Breakfast", phone_number="+263773344079")
    return f"✅ Grid test result: {result}"
