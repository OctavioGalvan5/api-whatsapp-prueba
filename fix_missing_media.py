from app import app, db, Message
from whatsapp_service import whatsapp_api
import os
import logging

# Configure basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

def fix_media():
    with app.app_context():
        # Get all messages that have a media_id (candidates for media)
        messages = Message.query.filter(Message.media_id.isnot(None)).all()
        logger.info(f"Checking {len(messages)} messages with media...")
        
        updated_count = 0
        
        for msg in messages:
            should_download = False
            
            # Case 1: No URL stored
            if not msg.media_url:
                logger.info(f"Message {msg.id}: No media_url stored. Downloading...")
                should_download = True
            
            # Case 2: URL stored but file missing
            else:
                # msg.media_url is like "static/media/filename.ext"
                # We need absolute path to check
                abs_path = os.path.join(os.getcwd(), msg.media_url.replace('/', os.sep))
                if not os.path.exists(abs_path):
                    logger.info(f"Message {msg.id}: File missing at {abs_path}. Redownloading...")
                    should_download = True
                else:
                    logger.info(f"Message {msg.id}: File OK.")
            
            if should_download:
                new_url = whatsapp_api.download_media(msg.media_id)
                if new_url:
                    if msg.media_url != new_url:
                        msg.media_url = new_url
                        updated_count += 1
                        logger.info(f"-> Saved as {new_url}")
                else:
                    logger.error(f"-> Failed to download media {msg.media_id}")
        
        if updated_count > 0:
            db.session.commit()
            logger.info(f"Updated {updated_count} messages in DB.")
        else:
            logger.info("No DB updates needed.")

if __name__ == "__main__":
    fix_media()
