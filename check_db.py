import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"

print("DB-Pfad:", DB_PATH)
print("Existiert DB?", DB_PATH.exists())

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Tabellen anzeigen
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = c.fetchall()
print("Tabellen:", tables)

# Events anzeigen
if ('events',) in tables:
    c.execute("SELECT * FROM events;")
    rows = c.fetchall()
    print("Events:")
    for r in rows:
        print(r)
else:
    print("Tabelle 'events' existiert nicht!")

conn.close()
