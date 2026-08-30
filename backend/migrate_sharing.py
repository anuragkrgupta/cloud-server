import sys
from app.database import SessionLocal
import sqlalchemy

db = SessionLocal()

try:
    db.execute(sqlalchemy.text("ALTER TABLE files ADD COLUMN is_shared BOOLEAN DEFAULT 0"))
    print("Added is_shared column.")
except Exception as e:
    print(f"Skipping is_shared: {e}")

try:
    db.execute(sqlalchemy.text("ALTER TABLE files ADD COLUMN share_token VARCHAR(255) UNIQUE"))
    print("Added share_token column.")
except Exception as e:
    print(f"Skipping share_token: {e}")
    
try:
    db.execute(sqlalchemy.text("CREATE INDEX ix_files_share_token ON files (share_token)"))
    print("Created index on share_token.")
except Exception as e:
    print(f"Skipping index: {e}")

db.commit()
db.close()
print("Migration complete!")
