import os
import psycopg2
from urllib.parse import urlparse

# Read DATABASE_URL from environment or hardcode for test
DATABASE_URL = os.getenv('DATABASE_URL') or "postgresql://email_assistant_db_2_user:yourpassword@dpg-d39qjn6mcj7s739ifmkg-a.singapore-postgres.render.com:5432/email_assistant_db_2"

def test_connection(db_url):
    try:
        # Parse the URL for psycopg2.connect kwargs
        result = urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path[1:]  # skip leading /
        hostname = result.hostname
        port = result.port

        conn = psycopg2.connect(
            dbname=database,
            user=username,
            password=password,
            host=hostname,
            port=port,
            sslmode='require'  # enforce SSL for Render
        )
        print("✅ Connection successful!")
        
        # Simple query test
        cur = conn.cursor()
        cur.execute("SELECT NOW();")
        now = cur.fetchone()
        print(f"Database time: {now[0]}")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_connection(DATABASE_URL)
