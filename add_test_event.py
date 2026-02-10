import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
INSERT INTO events (timestamp, event_type, video_file)
VALUES (?, ?, ?)
""", (
    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "motion",   # <- anderer Event-Typ
    None
))

conn.commit()
conn.close()

print("Zweiter Test-Event hinzugefügt")

