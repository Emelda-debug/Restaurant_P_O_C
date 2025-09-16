import os
from werkzeug.utils import secure_filename
import uuid
from supabase import create_client
import traceback
import logging
from config import SUPABASE_URL, SUPABASE_KEY

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_image_to_supabase(file):
    try:
        logger.info(f"Starting upload for file: {file.filename}")
        
        # Generate a unique filename
        ext = file.filename.rsplit('.', 1)[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        path = f"menu/{secure_filename(filename)}"
        
        logger.info(f"Generated path: {path}")
        
        file_data = file.read()
        content_type = file.content_type or "image/jpeg"
        
        logger.info(f"File size: {len(file_data)} bytes, Content type: {content_type}")
        logger.info(f"Attempting upload to bucket: taguta-menu-images")
        
        # Upload image to Supabase
        result = supabase.storage.from_("taguta-menu-items").upload(path, file_data, {"content-type": content_type})
        
        logger.info(f"Upload successful: {result}")
        
        # Build public URL
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/taguta-menu-items/{path}"
        logger.info(f"Generated public URL: {public_url}")
        
        return public_url
        
    except Exception as e:
        logger.error(f"Upload failed with error: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Try to get more specific error info
        if hasattr(e, 'response'):
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text}")
        
        raise e

# Add a function to list available buckets for debugging
def list_buckets():
    try:
        logger.info("Listing available buckets...")
        buckets = supabase.storage.list_buckets()
        logger.info(f"Available buckets: {buckets}")
        return buckets
    except Exception as e:
        logger.error(f"Failed to list buckets: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return None

# Add a function to check if bucket exists
def check_bucket_exists(bucket_name):
    try:
        logger.info(f"Checking if bucket '{bucket_name}' exists...")
        buckets = supabase.storage.list_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        exists = bucket_name in bucket_names
        logger.info(f"Bucket '{bucket_name}' exists: {exists}")
        logger.info(f"Available buckets: {bucket_names}")
        return exists
    except Exception as e:
        logger.error(f"Error checking bucket: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False
