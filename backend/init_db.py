import sys
import os

# Ensure the backend directory is in the sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base
from app.models import User, FileRecord, FilePartRecord

def init_db():
    print("Creating database tables...")
    try:
        # Create all tables defined in models.py
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        print("Please ensure your database server is running and the database 'cloud_db' exists.")

if __name__ == "__main__":
    init_db()
