import sys
import os

# Ensure the backend directory is in the sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine

def run_migration():
    print("Starting migration...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE file_parts ADD COLUMN channel_id VARCHAR(50)"))
            print("Added channel_id column to file_parts.")
        except Exception as e:
            if "Duplicate column name" in str(e) or "already exists" in str(e).lower() or "operationalerror" in str(e).lower():
                print("Column channel_id already exists or couldn't be added directly (maybe SQLite?).")
                print("Error details:", e)
            else:
                print("Error adding column:", e)
        
        try:
            # For PostgreSQL (Supabase)
            conn.execute(text("""
                UPDATE file_parts fp
                SET channel_id = u.channel_id
                FROM files f
                JOIN users u ON f.user_id = u.id
                WHERE fp.file_id = f.id
                AND fp.channel_id IS NULL
            """))
            print("Backfilled channel_id for PostgreSQL.")
        except Exception as e:
            print("PostgreSQL update failed, trying SQLite syntax...", e)
            try:
                # For SQLite
                conn.execute(text("""
                    UPDATE file_parts
                    SET channel_id = (
                        SELECT u.channel_id
                        FROM files f
                        JOIN users u ON f.user_id = u.id
                        WHERE f.id = file_parts.file_id
                    )
                    WHERE channel_id IS NULL
                """))
                print("Backfilled channel_id for SQLite.")
            except Exception as e2:
                print("SQLite update failed:", e2)
        
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    run_migration()
