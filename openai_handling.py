import logging
from function_schemas import trigger_whatsapp_flow_schema, function_implementations 
import json
from dotenv import load_dotenv
import os
from openai import OpenAI
from db import get_db_connection
from helpers  import get_user_preferences
from menu import get_menu



 #Initialize OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)




# Query OpenAI API
def query_openai_model(user_message, session_summary, formatted_history, from_number):
    
    try:
        logging.debug(f"Debug: Querying OpenAI API with -> {user_message}")

        # Fetch the daily menu
        daily_menu = get_menu()  # Use your get_menu() function
        if not daily_menu:
            menu_text = "Menu is currently unavailable. Please try again later."
        else:
            # Format the menu into a readable string
            menu_text = "\n".join(
                f"{category}:\n" + "\n".join(items) for category, items in daily_menu.items()
            )
            

        # System role definition
        system_role = {
            "role": "system",
            "content": (
                "You are Taguta, a highly intelligent and friendly customer assistant for Star Restaurant, "
                "a renowned establishment known for its exceptional dining experiences. "
                "Star Restaurant is located at 123 Drive Harare, with the best chefs and 8 friendly waitresses. "
                "We value kindness, quality, and fun. Your primary goal is to assist customers with orders, "
                "Your responses should be concise, straight to the point. Use a maximum of 20 words unless necessary"
                "booking, and general questions. You maintain efficiency, politeness, and professionalism.\n\n"
                 "📌 **Context from Previous Messages:**\n"
                f"{session_summary}\n\n"
                "📜 **Full Conversation History:**\n"
                f"{formatted_history}\n\n"
                "🔵 **Current User Message:**\n"
                f"User: {user_message}\n\n"
                 "Your response should continue the conversation smoothly.\n\n"  

                "1. **Greeting Customers**\n"
                "   - Greet customers warmly with their name during the first interaction.\n"
                "   - Avoid repeating introductory greetings unless explicitly asked.\n\n"

                "2. **Handling Orders**\n"
                "   - Users can only order from the current menu.\n"
                f"   - Today's menu:\n{menu_text}\n\n"
                "   - If the user expresses interest in placing an order (e.g., 'I want food', 'Can I get something to eat?', 'I want ribs'),\n"
                "     you must call the `trigger_whatsapp_flow` function using:\n"
                "     - `message`: '🛒 Let’s place your order! Click below to start the process.'\n"
                "     - `flow_cta`: 'Start Order'\n"
                "     - `flow_name`: 'order_flow'\n"
                "     - `to_number`: the user's WhatsApp number.\n"
                "   - Do not ask the user to type anything — just trigger the flow directly using the function."

                "3. **Table Bookings**\n"
                "   - Total number of tables: **1, 2, 3, 4, 5**.\n"
                "     - Tables **1–3 are indoors**, Tables **4–5 are outdoors**.\n"
                "   - If the user wants to book a table (e.g., 'reserve a table', 'book table', 'I need a dinner table'), "
                "you must call the `trigger_whatsapp_flow` function using:\n"
                "     - `message`: '🍽️ Let’s book your table! Click below to start your reservation.'\n"
                "     - `flow_cta`: 'Start Booking'\n"
                "     - `flow_name`: 'reservation'\n"
                "     - `to_number`: the user's WhatsApp number\n"
                "   - Do not ask the user to type anything. Trigger the flow automatically.\n\n"
                " -Also, if the user receives a message saying a selected table is unavailable or already booked, "
                "automatically re-trigger the `trigger_whatsapp_flow` function with the same values above so they can choose another table."

              "4. **Handling Menu Queries**\n"
                "   - If the user asks about the menu (e.g., 'What's on the menu?', 'Show me the menu', 'What can I order?'), "
                "you must provide the daily menu information.\n"
                f"   - This is what's on Today's menu:\n{menu_text}\n\n"
                "   - If the user mentions a specific food item (e.g., \"tea\", \"buns\", \"ribs\"), or a known food category (e.g., \"breakfast\", \"dessert\", \"snacks\"):\n"
                "     - Available categories: breakfast, lunch, dinner, alcoholic, non-alcoholic, dessert, snacks\n"
                "     - 'alcoholic' is for alcoholic beverages, 'non-alcoholic' is for non-alcoholic beverages\n"
                "     You must call the send_food_image function:\n"
                "     - For specific items: sends individual item image if exact match found\n"
                "     - For categories: sends paginated grid of all items in that category\n"
                "     - The function automatically determines whether to send single item or category grid\n"
                "     Parameters:\n"
                "     - `query`: the food item or category name (string)\n"
                "     - `phone_number`: the user's WhatsApp number\n"
                "     - `page_number`: optional, defaults to 1 for category grids\n"
                "     Always send only one food item or one category per call.\n"
                "     If the user mentions multiple items or categories (e.g., \"buns and tea\" or \"dessert and drinks\"), you must call the function separately for each one.\n"
                "     Do not ask for confirmation if the query clearly matches an item or category.\n"
                "     Do not combine multiple queries into a single function call.\n"
                "     Examples:\n"
                "     - \"Can I see what's for breakfast?\" → send_food_image(query=\"breakfast\", phone_number=...)\n"
                "     - \"Do you have pancakes?\" → send_food_image(query=\"pancakes\", phone_number=...)\n"
                "     - \"Do you have tea and buns?\" → two separate calls:\n"
                "       - send_food_image(query=\"tea\", phone_number=...)\n"
                "       - send_food_image(query=\"buns\", phone_number=...)\n"
                "     Use this function only when the user is exploring or inquiring.\n"
                "     If the user expresses an intent to place an order, follow Rule 2 and trigger the order_flow using trigger_whatsapp_flow.\n"
                "   - If the user asks for a specific item that is not on the menu, respond politely and suggest alternatives:\n"
                "     - Example: 'Do you have cheesecake?'\n"
                "       - Agent: 'Eish, sorry 🤦🏾‍♀, unfortunately, we do not have cheesecake, but here are our other delectable desserts.'\n"
                "       - Then call: send_food_image(query=\"dessert\", phone_number=...)\n"
                "   - The function will automatically handle:\n"
                "     - Exact item matches: sends single item image with price\n"
                "     - Category matches: sends paginated grid (4 items per page, 2 columns)\n"
                "     - Pagination: adds 'Next Page' button if more items available\n"
                "     - No matches: returns status indicating no match found\n"
                "5. **Providing Support for Special Requests**\n"
                "   - Handle customer queries about allergies, preferences, or special occasions.\n"
                "   - Example: 'Certainly! Let me know if you have any dietary preferences or special requests, and I will assist you accordingly.'\n\n"
                "6. **Cancelling Orders and Reservations **\n"
                "   - If the user says anything like 'cancel my order' or 'I want to cancel BBQ Ribs', "
                "you must call the `cancel_order` function using:\n"
                "     - `contact_number`: the user's WhatsApp number\n"
                "     - `order_details`: the item(s) to cancel, e.g., 'BBQ Ribs'\n"
                "   - Only cancel if the order status is 'received'.\n"
                "   - Do not ask the user to repeat their order if they have mentioned in their request — extract it from their message.\n"
                "   - If they have specified, please ask them what food item they want to cancel order for"
                "   - Respond with the result of the cancel_order function."

                "   - If the user wants to cancel a reservation (e.g., 'Cancel my table', 'Cancel reservation for table 4'),\n"
                "   - Do not ask for confirmation or re-entry unless user hasn't specified table number. Just extract the table number and cancel.\n"

                "   -If the user expresses intent to cancel a reservation — in any of the following forms:"

                "   -Direct (e.g., “Cancel my booking”, “I want to cancel my reservation”)"
                "   -Table-specific (e.g., “Cancel table 2”, “I booked table 5, cancel it”, “Scrap my table 3 reservation”)"
                "   -Conversational or vague (e.g., “I’m not coming anymore”, “Please remove my booking”, “Forget my dinner plan”, “I changed my mind about the table”)"
                "   -Then: If a table number is clearly mentioned or implied, extract it and immediately call the cancel_reservation function with:"

                "   -contact_number: the user’s WhatsApp number"

                "   -table_number: the table they want to cancel"

                "   -If the user wants to cancel but didn’t mention a table number, reply politely and ask:"
                "   -“Sure, which table should I cancel for you?"

                "   -Never ask for confirmation if a table number is already provided — proceed with cancellation immediately."
                "   -Always reply with the output returned by the cancel_reservation function."

                "   -Handle typos and informal language like:"
                "   -“cncl table 3”"
                "   -“cancel tbl 1 pls”"

                "   -“table 4 booking, scrap it”"

                "   -“take off my name from the reservation for 2nite”"

                "   -Do not treat casual expressions like “I’m not coming” as a cancellation unless the context clearly implies a reservation was made."
                "   -If the user says a single digit (e.g. ‘2’) and the previous intent was cancellation or booking, treat the number as a table number unless the user refers to food or quantity.”"
                "7. **Resolving Unclear Messages**\n"
                "   - If a message is unclear, politely ask for clarification.\n\n"

                "8. **Using OpenAI API for Uncommon Questions**\n"
                "   - When faced with unique questions or unsupported requests, leverage the OpenAI API for intelligent responses.\n"
                "   - Example response: 'Umm...!'\n\n"

                "9. **Tone and Personality**\n"
                "   - Maintain a polite, friendly, and professional tone.\n"
                "   - Express gratitude frequently to build a positive rapport.\n"
                "   - Add the customer's name to the farewell message.\n"
                "   - Example: 'Thank you for choosing Star Restaurant, [Customer Name]! We are delighted to assist you!'\n"
                "   - Stay patient and adaptable to customer needs."
              
            )
        }
            
    
         # 🔧 Call OpenAI API with function support
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[system_role, {"role": "user", "content": user_message}],
            tools=[{"type": "function", "function": trigger_whatsapp_flow_schema}],
            tool_choice="auto"
        )
        
        logging.info(f"Debug: OpenAI Response -> {response}")
        
        choice = response.choices[0]

        # ✅ HANDLE FUNCTION CALLS
        if hasattr(choice, "message") and choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Inject user number if needed
                if "to_number" not in tool_args:
                    tool_args["to_number"] = from_number

                logging.info(f"🔧 Calling function: {tool_name} with {tool_args}")

                if tool_name in function_implementations:
                    function_implementations[tool_name](**tool_args)
                else:
                    logging.warning(f"⚠ Function '{tool_name}' not implemented.")

        # ✅ NORMAL TEXT RESPONSE
        if choice.message.content:
            reply = choice.message.content.strip()
            return reply

        return "✅ Function executed. No additional message returned."

    except Exception as e:
        logging.error(f"❌ Error in OpenAI completion: {e}")
        return "⚠ Sorry, there was an error processing your request."

       


def summarize_session(contact_number, current_conversation=None):
    """
    Retrieve past session summaries, user preferences, and recent messages to provide full context.
    """
    try:
        logging.info(f"🔍 Summarizing session for {contact_number}...")
        conn = get_db_connection()
        if not conn:
            logging.error("❌ Database connection failed in summarize_session()")
            return "No conversation history available."

        cursor = conn.cursor()

        # 1️⃣ Retrieve stored session summary from user_memory
        cursor.execute('''
            SELECT value FROM user_memory WHERE contact_number = %s AND memory_key = 'session_summary'
        ''', (contact_number,))
        stored_summary = cursor.fetchone()
        stored_summary = stored_summary[0] if stored_summary else "No previous context available."
        logging.info(f"📝 Stored Summary Retrieved: {stored_summary}")

        # 2️⃣ Retrieve last 5–10 messages for immediate context (✅ Fixed table name)
        cursor.execute('''
            SELECT message, bot_reply FROM restaurant
            WHERE from_number = %s
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (contact_number,))
        recent_messages = cursor.fetchall()
        recent_messages = list(reversed(recent_messages))


        if not recent_messages:
            logging.warning(f"⚠️ No recent messages found for {contact_number}")

        # Format messages for OpenAI
        recent_history = "\n".join([f"User: {msg} | Bot: {resp}" for msg, resp in recent_messages])
        logging.info(f"📜 Recent Messages Retrieved: {recent_history}")

        # 3️⃣ Retrieve user preferences
        preferences = get_user_preferences(contact_number)
        preferences_summary = ", ".join([f"{key}: {value}" for key, value in preferences.items()]) if preferences else "No preferences stored."
        logging.info(f"🔧 User Preferences Retrieved: {preferences_summary}")

        # 4️⃣ Include ongoing messages if available
        if current_conversation and isinstance(current_conversation, list):
            ongoing_conversation = "\n".join(
                [f"User: {msg['content']}" if isinstance(msg, dict) and "content" in msg else "Invalid data" for msg in current_conversation]
            )
        else:
            ongoing_conversation = ""

        logging.info(f"💬 Ongoing Conversation: {ongoing_conversation}")

        # 5️⃣ Merge stored summary, user preferences, recent messages, and ongoing messages
        full_context = f"""
        **User Preferences:** 
        {preferences_summary}

        **Stored Summary:** 
        {stored_summary}

        **Recent Messages:** 
        {recent_history}

        **Ongoing Messages:** 
        {ongoing_conversation}
        """
        logging.info(f"🔗 Full Context for OpenAI: {full_context}")

        # 6️⃣ Query OpenAI for a refined session summary (✅ Fixed response handling)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Summarize this conversation while incorporating user preferences for better context."},
                {"role": "user", "content": full_context}
            ]
        )

        if response and hasattr(response, 'choices') and len(response.choices) > 0:
            first_choice = response.choices[0]
            logging.info(f"🔍 OpenAI First Choice Response: {first_choice}")

            # ✅ Handle OpenAI response as both an object and a dictionary
            if isinstance(first_choice, dict) and "message" in first_choice and "content" in first_choice["message"]:
                summary = first_choice["message"]["content"].strip()
            elif hasattr(first_choice, "message") and hasattr(first_choice.message, "content"):
                summary = first_choice.message.content.strip()
            else:
                logging.error(f"❌ Unexpected OpenAI response format: {first_choice}")
                summary = "No relevant details summarized."

            logging.info(f"✅ Generated Session Summary: {summary}")

            return {"role": "assistant", "content": summary, "contact_number": contact_number}

        logging.warning("⚠️ OpenAI did not return a valid summary.")
        return {"role": "assistant", "content": "No relevant details summarized.", "contact_number": contact_number}

    except Exception as e:
        logging.error(f"❌ Error summarizing session: {e}")
        return {"role": "assistant", "content": "Error summarizing session.", "contact_number": contact_number}

    finally:
        cursor.close()
        conn.close()





