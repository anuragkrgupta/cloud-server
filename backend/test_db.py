import sys
import logging
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_db_connection():
    try:
        logger.info(f"Connecting to database using URL: {engine.url}")
        with engine.connect() as conn:
            logger.info("Success! Connected to the database.")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_db_connection()
