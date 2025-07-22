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
os.environ['META_PHONE_NUMBER_ID'] 
os.environ['META_ACCESS_TOKEN']
os.environ['OPENAI_API_KEY'] 
# Admin number to send periodic updates
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')



bcrypt = Bcrypt()

