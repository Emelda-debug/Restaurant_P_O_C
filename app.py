import traceback
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Blueprint
from menu import send_food_image
import psycopg2
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



# Load environment variables from .env file
load_dotenv()

# Configure Logging
logging.basicConfig(
    filename="app.log",  
    level=logging.DEBUG,  
    format="%(asctime)s - %(levelname)s - %(message)s"
)




dash_blueprint = Blueprint('dash', __name__)
 




def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname="restaurant",
            user="postgres",
            password="postgres", 
            host=os.getenv("DB_HOST", "db"),  
            port="5432"
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection error: {e}")
        return None


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

    conn = get_db_connection()
    if not conn:
        logging.debug("Debug: Database connection is None, returning False")
        return False

    try:
        cursor = conn.cursor()
        logging.info("Debug: Executing query to fetch password hash")
        cursor.execute("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
        row = cursor.fetchone()

        if row:
            logging.info("Debug: User found in database, verifying password")
            if bcrypt.check_password_hash(row[0], password):
                logging.info("Debug: Password verification successful")
                return True
            else:
                logging.debug("Debug: Password verification failed")
        else:
            logging.info("Debug: No user found with the given username")

    except psycopg2.Error as e:
        logging.debug(f"Debug: Database error while verifying password: {e}")

    finally:
        cursor.close()
        conn.close()
        logging.debug("Debug: Database connection closed")
    logging.debug("Debug: Returning False from verify_password")
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
            return redirect(url_for('dash.dashboard'))
        else:
            logging.error("Authentication failed, rendering login page with error")
            return render_template('index.html', error="Invalid username or password")

    logging.debug("Debug: Rendering login page")
    return render_template('index.html')



@dash_blueprint.route('/dashboard')
def dashboard():
    """
    Fetch key metrics for the restaurant dashboard.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))
    # Get user's profile image
    user_profile_image = None
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_image FROM admin_users WHERE username = %s", (session['user'],))
            result = cursor.fetchone()
            if result and result[0]:
                user_profile_image = result[0]
        except Exception as e:
            logging.error(f"Error fetching profile image: {e}")
        finally:
            cursor.close()
            conn.close()

    conn = get_db_connection()
    if not conn:
        logging.error("❌ Database connection failed.")
        return render_template("d.html", error="Database connection failed")

    try:
        cursor = conn.cursor()

        # Fetching all required data
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'done'")
        completed_orders = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('done', 'cancelled')")
        pending_orders = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM reservations")
        total_reservations = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM restaurant_tables WHERE is_available = TRUE")
        available_tables = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM customers")
        total_customers = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("SELECT COUNT(*) FROM menu WHERE available = TRUE")
        total_menu_items = cursor.fetchone()[0] if cursor.rowcount else 0

        cursor.execute("""
            SELECT rating, COUNT(*) 
            FROM orders 
            WHERE rating IS NOT NULL
            GROUP BY rating
            ORDER BY rating DESC
        """)
        ratings_data = cursor.fetchall()
        cursor.execute("""
            SELECT TO_CHAR(created_at, 'Mon') AS month, COUNT(*) 
            FROM orders 
            GROUP BY month 
            ORDER BY MIN(created_at)
        """)
        monthly_orders = cursor.fetchall()  


        cursor.execute("""
            SELECT order_details, COUNT(*) as order_count
            FROM orders
            WHERE order_details IS NOT NULL
            GROUP BY order_details
            ORDER BY order_count DESC
            LIMIT 5;
        """)
        top_menu_items = cursor.fetchall()

        cursor.close()
        conn.close()

        # Render the dashboard with data
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

    except psycopg2.Error as e:
        logging.error(f"❌ Database error: {e}")
        return render_template("d.html", error="Error fetching dashboard data")




@dash_blueprint.route('/menus', methods=['GET', 'POST'])
def menus():
    """
    Manage menus (view, add, bulk upload via Excel).
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        if request.method == 'POST':
            file = request.files.get('file')

            if file and file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(file, engine='openpyxl')

                    required_columns = {'Category', 'Item Name', 'Price', 'Available'}
                    if required_columns.issubset(df.columns):
                        for _, row in df.iterrows():
                            if pd.isna(row['Category']) or pd.isna(row['Item Name']) or pd.isna(row['Price']) or pd.isna(row['Available']):
                                logging.info(f"Skipping row due to missing data: {row}")
                                continue  # Skip this row

                            category = row['Category']
                            item_name = row['Item Name']
                            price = row['Price']
                            available = bool(row['Available'])  # Convert to boolean (True/False)

                            # Insert new menu item only if it doesn't exist
                            cursor.execute('''
                                INSERT INTO menu (category, item_name, price, available)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (item_name) DO NOTHING
                            ''', (category, item_name, price, available))

                        conn.commit()
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
                        check_bucket_exists("taguta-menu-items")
                        image_url = upload_image_to_supabase(image_file)
                    except Exception as e:
                        logging.error(f"Main app upload error: {str(e)}")
                        logging.error(f"Full traceback: {traceback.format_exc()}")

                cursor.execute('''
                    INSERT INTO menu (category, item_name, price, available, image_url)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (item_name) DO NOTHING
                ''', (category, item_name, price, available, image_url))
                conn.commit()

        cursor.execute('SELECT * FROM menu')
        menus = cursor.fetchall()

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching menu items: {e}")
        menus = []

    finally:
        cursor.close()
        conn.close()

    return render_template('menus.html', menus=menus)




@dash_blueprint.route('/edit_menu/<int:menu_id>', methods=['POST'])
def edit_menu(menu_id):
    """
    Edit a menu item.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
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

        # Build the update query
        if image_url:
            cursor.execute('''
                UPDATE menu
                SET category=%s, item_name=%s, price=%s, available=%s, image_url=%s
                WHERE id=%s
            ''', (category, item_name, price, available, image_url, menu_id))
        else:
            cursor.execute('''
                UPDATE menu
                SET category=%s, item_name=%s, price=%s, available=%s
                WHERE id=%s
            ''', (category, item_name, price, available, menu_id))
        conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Database error while editing menu item: {e}")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dash.menus'))


@dash_blueprint.route('/conversations', methods=['GET'])
def conversations():
    """
    Fetch and display all user-bot conversations, ensuring names are correctly fetched.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    # Get filter parameters
    phone_filter = request.args.get('phone_filter', '').strip()
    name_filter = request.args.get('name_filter', '').strip().lower()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    try:
        cursor = conn.cursor()

        # Fetch all messages without relying on SQL JOIN for names
        query = """
            SELECT from_number, message, bot_reply, timestamp 
            FROM restaurant
        """
        conditions = []
        params = []

        if phone_filter:
            conditions.append("from_number LIKE %s")
            params.append(f"%{phone_filter}%")  # Allow partial search

    
        if start_date and end_date:
            conditions.append("DATE(timestamp) BETWEEN %s AND %s")
            params.append(start_date)
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY from_number, timestamp ASC"

        cursor.execute(query, params)
        raw_messages = cursor.fetchall()

        transcripts = {}

        if raw_messages:
            for msg in raw_messages:
                phone_number = msg[0]
                customer_name = get_customer_name(phone_number)  # Fetch name using function

                # Apply name filter in Python instead of SQL
                if name_filter and name_filter not in customer_name.lower():
                    continue  # Skip this conversation if name does not match
                
                if phone_number not in transcripts:
                    transcripts[phone_number] = {"name": customer_name, "messages": []}
                transcripts[phone_number]["messages"].append({
                    "message": msg[1],
                    "bot_reply": msg[2],
                    "timestamp": msg[3]
                })

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching conversations: {e}")
        transcripts = {}

    finally:
        cursor.close()
        conn.close()

    return render_template('conversations.html', transcripts=transcripts, phone_filter=phone_filter, name_filter=name_filter, start_date=start_date, end_date=end_date)


@dash_blueprint.route('/menus/delete/<int:menu_id>', methods=['POST'])
def delete_menu_item(menu_id):
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM menu WHERE id = %s', (menu_id,))
        conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Database error while deleting menu item: {e}")
        return "An error occurred while deleting the menu item.", 500
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dash.menus'))


@dash_blueprint.route('/set_highlight/<int:menu_id>', methods=['POST'])
def set_highlight(menu_id):
    """
    Set a menu item as the highlight of the day.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        # Reset all highlights
        cursor.execute('UPDATE menu SET highlight = FALSE')

        # Set the selected item as the highlight
        cursor.execute('UPDATE menu SET highlight = TRUE WHERE id = %s', (menu_id,))

        conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Database error while setting highlight: {e}")
        return "There was an issue setting the highlight. Please try again later."
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('menus'))


@dash_blueprint.route('/reservations')
def reservations():
    """
    View all active reservations.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE reservations_done = FALSE')
        reservations = cursor.fetchall()

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching reservations: {e}")
        reservations = []

    finally:
        cursor.close()
        conn.close()

    return render_template('reservations.html', reservations=reservations)




@dash_blueprint.route('/free-table/<int:reservation_id>', methods=['POST'])
def free_table(reservation_id):
    """
    Free up a table after a reservation is completed.
    """
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        # Get table number and contact number from the reservation
        cursor.execute('SELECT table_number, contact_number FROM reservations WHERE id = %s', (reservation_id,))
        reservation = cursor.fetchone()

        if not reservation:
            return "Reservation not found.", 404
        
        table_number, contact_number = reservation

        # Update the table's availability
        cursor.execute('UPDATE restaurant_tables SET is_available = TRUE WHERE table_number = %s', (table_number,))

        # Mark reservation as done
        cursor.execute('UPDATE reservations SET reservations_done = TRUE WHERE id = %s', (reservation_id,))

        conn.commit()

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

    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        return "Error freeing table.", 500

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('reservations'))



@dash_blueprint.route('/orders')
def orders():
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE status IN (%s, %s)', ('received', 'in-transit'))
        orders = cursor.fetchall()
    except psycopg2.Error as e:
        logging.error(f"Database error while fetching orders: {e}")
        orders = []
    finally:
        cursor.close()
        conn.close()

    return render_template('orders.html', orders=orders)



@dash_blueprint.route('/orders/done/<int:order_id>', methods=['POST'])
def mark_order_done(order_id):
    flow_id = 1146774760431392
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE orders SET status = %s WHERE id = %s', ('done', order_id))
        conn.commit()

        cursor.execute('SELECT contact_number, order_details FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()

        if order:
            contact_number, order_details = order
            message = (
                f"Your order for '{order_details}' has been marked as done. "
                "Thank you for choosing Star Restaurant! 🌟\n\n"
                "We value your feedback! Please rate your experience below."
            )
            
            flow_cta = "Rate Your Ordering Experience"  
            flow_name = "order_rating"

        flow_response = trigger_whatsapp_flow(contact_number, message, flow_cta, flow_name)
        logging.debug(f"🔍 Flow Trigger Debug - User: {contact_number}, Response: {flow_response}")

    except psycopg2.Error as e:
        logging.error(f"Database error while updating order: {e}")
        return "Error marking the order as done.", 500
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('orders'))


@dash_blueprint.route('/ratings')
def ratings():
    """
    View all ratings for completed orders and reservations.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        # Fetch ratings for orders
        cursor.execute('''
            SELECT id, contact_number, order_details AS details, rating, 'Order' AS type 
            FROM orders 
            WHERE rating IS NOT NULL
        ''')
        order_ratings = cursor.fetchall()

        # Fetch ratings for reservations
        cursor.execute('''
            SELECT id, contact_number, name AS details, rating, 'Reservation' AS type 
            FROM reservations 
            WHERE rating IS NOT NULL
        ''')
        reservation_ratings = cursor.fetchall()

        # Combine both lists into one
        ratings = order_ratings + reservation_ratings  

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching ratings: {e}")
        ratings = []

    finally:
        cursor.close()
        conn.close()

    return render_template('ratings.html', ratings=ratings)




@dash_blueprint.route('/orders/in-transit/<int:order_id>', methods=['POST'])
def mark_order_in_transit(order_id):
    """
    Mark an order as 'in-transit'.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))
    
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        # Update the order status to 'in-transit'
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", ('in-transit', order_id))
        conn.commit()
        
        # Retrieve contact number and order details
        cursor.execute("SELECT contact_number, order_details FROM orders WHERE id = %s", (order_id,))
        order = cursor.fetchone()
        
        if order:
            contact_number, order_details = order
            message = f"Your order for '{order_details}' is now in transit. Expect it shortly!"
            notify_user(contact_number, message)

    except psycopg2.Error as e:
        logging.error(f"Database error while updating order: {e}")
        return "Error marking the order as in-transit.", 500

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('orders'))



@dash_blueprint.route('/contacts', methods=['GET', 'POST'])
def contacts():
    """
    Manage contacts (view, add, bulk upload via Excel).
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()

        if request.method == 'POST':
            file = request.files.get('file')

            if file and file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(file, engine='openpyxl')
                    
                    if {'Name', 'Contact Number'}.issubset(df.columns):
                        for _, row in df.iterrows():
                            name = row['Name']
                            contact_number = row['Contact Number']
                            status = 'new'

                            cursor.execute('''
                                INSERT INTO customers (name, contact_number, status)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (contact_number) DO NOTHING
                            ''', (name, contact_number, status))

                        conn.commit()
                    else:
                        logging.error("Error: Missing required columns (Name, Contact Number)")
                
                except Exception as e:
                    logging.error(f"Error processing Excel file: {e}")

            elif 'name' in request.form and 'contact_number' in request.form:
                name = request.form['name']
                contact_number = request.form['contact_number']
                status = 'new'

                cursor.execute('''
                    INSERT INTO customers (name, contact_number, status)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (contact_number) DO NOTHING
                ''', (name, contact_number, status))
                conn.commit()

        cursor.execute('SELECT name, contact_number, status FROM customers')
        contacts = cursor.fetchall()

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching contacts: {e}")
        contacts = []

    finally:
        cursor.close()
        conn.close()

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
    Delete a contact by its contact number.
    """
    if 'user' not in session:
        return redirect(url_for('dash.login'))
    
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM customers WHERE contact_number = %s", (contact_number,))
        conn.commit()

    except psycopg2.Error as e:
        logging.error(f"Database error while deleting contact: {e}")
        return "Error deleting the contact.", 500

    finally:
        cursor.close()
        conn.close()

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
    Display individual chat conversation with bubble interface.
    """
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor()
        
        # Fetch messages for the specific phone number
        cursor.execute("""
            SELECT message, bot_reply, timestamp 
            FROM restaurant 
            WHERE from_number = %s 
            ORDER BY timestamp ASC
        """, (phone,))
        
        raw_messages = cursor.fetchall()
        
        # Format messages for template
        messages = []
        for msg in raw_messages:
            messages.append({
                "message": msg[0],
                "bot_reply": msg[1],
                "timestamp": msg[2]
            })
        
        # Get customer name
        customer_name = get_customer_name(phone)
        
        return render_template('chat.html', 
                             messages=messages, 
                             customer_name=customer_name, 
                             phone_number=phone)

    except psycopg2.Error as e:
        logging.error(f"Database error while fetching chat for {phone}: {e}")
        return "Database error", 500

    finally:
        cursor.close()
        conn.close()


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

    # Get current user's profile image
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_image FROM admin_users WHERE username = %s", (session['user'],))
            result = cursor.fetchone()
            if result and result[0]:
                user_profile_image = result[0]
        except Exception as e:
            logging.error(f"Error fetching profile image: {e}")
        finally:
            cursor.close()
            conn.close()

    if request.method == 'POST':
        conn = get_db_connection()
        if not conn:
            error_message = "Database connection failed"
        else:
            try:
                cursor = conn.cursor()
                
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
                        cursor.execute(
                            "UPDATE admin_users SET password_hash = %s WHERE username = %s",
                            (new_password_hash, session['user'])
                        )
                        conn.commit()
                        success_message = "Password updated successfully"
                
                # Handle profile picture update
                elif 'update_profile' in request.form:
                    profile_image = request.files.get('profile_image')
                    if profile_image and profile_image.filename:
                        # Create uploads directory if it doesn't exist
                        import os
                        upload_dir = os.path.join('static', 'uploads')
                        os.makedirs(upload_dir, exist_ok=True)
                        
                        # Save the file
                        filename = f"profile_{session['user']}.{profile_image.filename.split('.')[-1]}"
                        filepath = os.path.join(upload_dir, filename)
                        profile_image.save(filepath)
                        
                        # Update database with new profile image path
                        cursor.execute(
                            "UPDATE admin_users SET profile_image = %s WHERE username = %s",
                            (f"uploads/{filename}", session['user'])
                        )
                        conn.commit()
                        success_message = "Profile picture updated successfully"
                        
                        # Update the user_profile_image variable for immediate display
                        user_profile_image = f"uploads/{filename}"
                    else:
                        error_message = "Please select a valid image file"
                        
            except Exception as e:
                logging.error(f"Error updating profile: {e}")
                error_message = "An error occurred while updating your profile"
            finally:
                cursor.close()
                conn.close()

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
    
    # Check if current user is admin
    conn = get_db_connection()
    if not conn:
        return redirect(url_for('dash.dashboard'))
    
    user_role = None
    user_profile_image = None
    

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role, profi;e_image FROM admin_users WHERE username = %s", (session['user'],))
        result = cursor.fetchone()
        user_role = result[0] if result else 'user'
        user_profile_image = result[1] if result and result[1] else None 

        
        if user_role != 'admin':
            return redirect(url_for('dash.forbidden', user_role=user_role))
            
    except Exception as e:
        logging.error(f"Error checking user role: {e}")
        return redirect(url_for('dash.forbidden', user_role='user'))
    finally:
        cursor.close()
        conn.close()

    # Rest of your existing add_user code...
    success_message = None
    error_message = None
    users = []

    if request.method == 'POST':
        username = request.form.get('username')
        role = request.form.get('role', 'user')
        
        if not username:
            error_message = "Username is required"
        else:
            conn = get_db_connection()
            if not conn:
                error_message = "Database connection failed"
            else:
                try:
                    cursor = conn.cursor()
                    
                    # Check if username already exists
                    cursor.execute("SELECT username FROM admin_users WHERE username = %s", (username,))
                    if cursor.fetchone():
                        error_message = "Username already exists"
                    else:
                        # Hash the default password
                        default_password = "taguta"
                        password_hash = bcrypt.generate_password_hash(default_password).decode('utf-8')
                        
                        # Insert new user
                        cursor.execute(
                            "INSERT INTO admin_users (username, password_hash, role, created_at) VALUES (%s, %s, %s, NOW())",
                            (username, password_hash, role)
                        )
                        conn.commit()
                        success_message = f"User '{username}' created successfully with default password 'taguta'"
                        
                except Exception as e:
                    logging.error(f"Error creating user: {e}")
                    error_message = "An error occurred while creating the user"
                finally:
                    cursor.close()
                    conn.close()
    

    # Fetch all users to display
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT username, role, created_at FROM admin_users ORDER BY created_at DESC")
            users = [{'username': row[0], 'role': row[1], 'created_at': row[2]} for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error fetching users: {e}")
        finally:
            cursor.close()
            conn.close()

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
