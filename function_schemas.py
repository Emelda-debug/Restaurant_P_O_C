from whatsapp_utils import trigger_whatsapp_flow
from orders import cancel_order
from reservations import cancel_reservation
from menu import send_food_image


function_implementations = {
    "trigger_whatsapp_flow": trigger_whatsapp_flow,
    "cancel_order": cancel_order,
    "cancel_reservation": cancel_reservation,
    "send_food_image": send_food_image,

}

trigger_whatsapp_flow_schema ={
  "name": "trigger_whatsapp_flow",
  "description": "Triggers a WhatsApp Flow by sending a structured interactive message to the user.",
  "parameters": {
    "type": "object",
    "required": ["to_number", "message", "flow_cta", "flow_name"],
    "properties": {
      "to_number": {
        "type": "string",
        "description": "The WhatsApp number of the user in E.164 format (e.g., +2637XXXXXXX)."
      },
      "message": {
        "type": "string",
        "description": "The friendly message text that appears before the WhatsApp Flow starts."
      },
      "flow_cta": {
        "type": "string",
        "description": "The label for the call-to-action button (e.g., 'Start Order')."
      },
      "flow_name": {
        "type": "string",
        "enum": ["order_flow", "reservation"],
        "description": "The internal reference name for the WhatsApp Flow to be triggered."
      }
    },
    "additionalProperties": False
  }
}


cancel_order_schema = {
    "name": "cancel_order",
    "description": "Cancels an order if it has not yet been processed (status must be 'received').",
    "parameters": {
        "type": "object",
        "required": ["contact_number", "order_details"],
        "properties": {
            "contact_number": {
                "type": "string",
                "description": "The WhatsApp number of the user who placed the order."
            },
            "order_details": {
                "type": "string",
                "description": "The exact item(s) in the order to be canceled (e.g., 'BBQ Ribs, Mojito')."
            }
        },
        "additionalProperties": False
    }
}

cancel_reservation_schema = {
    "name": "cancel_reservation",
    "description": "Cancels a reservation for a specific table made by a contact number, and marks the table as available again.",
    "parameters": {
        "type": "object",
        "required": ["contact_number", "table_number"],
        "properties": {
            "contact_number": {
                "type": "string",
                "description": "The WhatsApp number of the user who made the reservation."
            },
            "table_number": {
                "type": "integer",
                "description": "The number of the table to cancel the reservation for (e.g., 3)."
            }
        },
        "additionalProperties": False
    }
}

send_menu_item_image = {
    "name": "send_food_image",
    "description": "Sends an image of a specific menu item (if exact match) or a paginated grid of items (if category match). Handles both individual items and categories automatically.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The name of the menu item (e.g., 'Pancakes', 'Tea') or category (e.g., 'breakfast', 'lunch', 'dinner', 'alcoholic', 'non-alcoholic', 'dessert', 'snacks')"
            },
            "phone_number": {
                "type": "string",
                "description": "The user's WhatsApp phone number"
            },
            "page_number": {
                "type": "integer",
                "description": "Page number for category results (default: 1)",
                "default": 1
            }
        },
        "required": ["query", "phone_number"]
    }
}


# ✅ Export list of schemas (add more later if needed)
function_schemas = [
    trigger_whatsapp_flow_schema,
    cancel_order_schema,
    cancel_reservation_schema,
    send_menu_item_image
    ]
