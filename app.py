from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
import os

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"
VIDEO_DIR = BASE_DIR / "static" / "videos"

# Erstelle den Video-Ordner, falls nicht vorhanden
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            video_file TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_event(event_type, video_filename=None):
    """Fügt einen neuen Event-Eintrag in die Datenbank hinzu"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Stelle sicher, dass .mp4 Endung vorhanden ist
    if video_filename and not video_filename.endswith('.mp4'):
        video_filename = video_filename + '.mp4'
    
    c.execute("""
        INSERT INTO events (timestamp, event_type, video_file)
        VALUES (?, ?, ?)
    """, (timestamp, event_type, video_filename))
    conn.commit()
    conn.close()

def get_events(limit=None):
    """Holt Events aus der Datenbank"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if limit:
        c.execute("""
            SELECT id, timestamp, event_type, video_file
            FROM events
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
    else:
        c.execute("""
            SELECT id, timestamp, event_type, video_file
            FROM events
            ORDER BY timestamp DESC
        """)
    
    rows = c.fetchall()
    conn.close()
    
    # Konvertiere zu Dictionary
    events_list = []
    for row in rows:
        event = dict(row)
        events_list.append(event)
    
    return events_list

def get_event_by_id(event_id):
    """Holt ein spezifisches Event anhand der ID"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, timestamp, event_type, video_file
        FROM events
        WHERE id = ?
    """, (event_id,))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def get_event_stats():
    """Gibt Statistiken über die Events zurück"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Gesamtanzahl
    c.execute("SELECT COUNT(*) FROM events")
    total = c.fetchone()[0]
    
    # Anzahl Ring-Events
    c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'ring'")
    rings = c.fetchone()[0]
    
    # Anzahl Motion-Events
    c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'motion'")
    motions = c.fetchone()[0]
    
    # Letztes Event
    c.execute("SELECT timestamp FROM events ORDER BY timestamp DESC LIMIT 1")
    last_event = c.fetchone()
    last_timestamp = last_event[0] if last_event else "Keine Events"
    
    conn.close()
    
    return {
        'total': total,
        'rings': rings,
        'motions': motions,
        'last_event': last_timestamp
    }

@app.route("/")
def dashboard():
    """Haupt-Dashboard mit Event-Buttons"""
    events = get_events(limit=20)  # Nur die 20 neuesten Events
    stats = get_event_stats()
    return render_template("dashboard.html", events=events, stats=stats)

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    """Detailseite für ein spezifisches Event"""
    event = get_event_by_id(event_id)
    if not event:
        return "Event nicht gefunden", 404
    
    return render_template("event_detail.html", event=event)

@app.route("/api/events/recent")
def api_recent_events():
    """API für die neuesten Events (kann für AJAX-Updates verwendet werden)"""
    events = get_events(limit=10)
    return jsonify(events)

@app.route("/add_event", methods=["POST"])
def api_add_event():
    """API-Endpunkt zum Hinzufügen eines Events"""
    event_type = request.form.get("event_type", "unknown")
    
    video_filename = None
    if 'video' in request.files:
        video_file = request.files['video']
        if video_file.filename != '':
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = f"{event_type}_{timestamp}.mp4"
            video_path = VIDEO_DIR / video_filename
            video_file.save(video_path)
    
    add_event(event_type, video_filename)
    
    return jsonify({"status": "success", "video_filename": video_filename})

@app.route("/static/videos/<filename>")
def serve_video(filename):
    """Dient Videos aus dem Videos-Ordner"""
    # Füge .mp4 hinzu, falls nicht vorhanden
    if not filename.endswith('.mp4'):
        filename = filename + '.mp4'
    
    return send_from_directory(VIDEO_DIR, filename)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

