from dotenv import load_dotenv
import os
import logging
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt


# Load environment variables from .env file
load_dotenv()

db = SQLAlchemy()

# Configure Logging
logging.basicConfig(
    filename="agent.log",  
    level=logging.DEBUG,  
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Set up environment variables for Meta API
META_PHONE_NUMBER_ID = os.getenv('META_PHONE_NUMBER_ID')
META_ACCESS_TOKEN = os.getenv('META_ACCESS_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
# Admin number to send periodic updates
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')



bcrypt = Bcrypt()

