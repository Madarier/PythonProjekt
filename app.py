from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
import os
import threading
import time
import RPi.GPIO as GPIO

app = Flask(__name__)

# Pin-Definitionen für Pi-Top (BCM-Nummern!)
BUTTON_PIN = 26        # D2 = GPIO26 (BCM)
ULTRASONIC_TRIG = 13   # D7 = GPIO13 (BCM) für TRIG
ULTRASONIC_ECHO = 6    # D7 = GPIO6 (BCM) für ECHO

# Globale Variablen
sensor_active = True
last_button_state = True  # True = nicht gedrückt (wegen Pull-Up)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"
VIDEO_DIR = BASE_DIR / "static" / "videos"

# Erstelle den Video-Ordner, falls nicht vorhanden
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

def init_gpio():
    """Initialisiert die GPIO-Pins für Pi-Top"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)  # Warnungen deaktivieren
        
        # Button mit Pull-Up Widerstand (D2)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Ultraschallsensor (D7)
        GPIO.setup(ULTRASONIC_TRIG, GPIO.OUT)
        GPIO.setup(ULTRASONIC_ECHO, GPIO.IN)
        
        # Initialisiere TRIG auf LOW
        GPIO.output(ULTRASONIC_TRIG, False)
        time.sleep(0.5)
        
        print("GPIO für Pi-Top initialisiert")
        print(f"Button an GPIO{BUTTON_PIN} (D2)")
        print(f"Ultraschall TRIG an GPIO{ULTRASONIC_TRIG} (D7)")
        print(f"Ultraschall ECHO an GPIO{ULTRASONIC_ECHO} (D7)")
        
    except Exception as e:
        print(f"Fehler bei GPIO-Initialisierung: {e}")
        raise

def get_distance():
    """Misst die Distanz mit dem Ultraschallsensor"""
    try:
        # Trigger auf HIGH setzen
        GPIO.output(ULTRASONIC_TRIG, True)
        time.sleep(0.00001)  # 10µs
        GPIO.output(ULTRASONIC_TRIG, False)
        
        pulse_start = time.time()
        pulse_end = time.time()
        
        # Warte auf Echo START
        timeout_start = time.time()
        while GPIO.input(ULTRASONIC_ECHO) == 0:
            pulse_start = time.time()
            if time.time() - timeout_start > 0.1:
                return None
        
        # Warte auf Echo ENDE
        timeout_start = time.time()
        while GPIO.input(ULTRASONIC_ECHO) == 1:
            pulse_end = time.time()
            if time.time() - timeout_start > 0.1:
                return None
        
        # Distanz berechnen
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Schallgeschwindigkeit in cm/s geteilt durch 2
        distance = round(distance, 2)
        
        # Plausibilitätsprüfung
        if 2 < distance < 400:  # Gültiger Bereich 2-400 cm
            return distance
        else:
            return None
            
    except Exception as e:
        print(f"Fehler bei Distanzmessung: {e}")
        return None

def check_button():
    """Prüft den Button-Status manuell"""
    global last_button_state
    
    try:
        current_state = GPIO.input(BUTTON_PIN)
        
        # Button wurde gedrückt (von HIGH auf LOW)
        if last_button_state == True and current_state == False:
            print(f"[BUTTON] Button an GPIO{BUTTON_PIN} wurde betätigt!")
            # Optional: Event in Datenbank speichern
            # add_event("ring")
            return True
        
        # Button wurde losgelassen (von LOW auf HIGH)
        elif last_button_state == False and current_state == True:
            print(f"[BUTTON] Button an GPIO{BUTTON_PIN} wurde losgelassen!")
            return False
        
        last_button_state = current_state
        return None
        
    except Exception as e:
        print(f"Fehler bei Button-Check: {e}")
        return None

def sensor_thread():
    """Thread für regelmäßige Sensoren-Überwachung"""
    print("Sensor-Thread gestartet")
    
    while sensor_active:
        try:
            # Ultraschall-Messung
            distance = get_distance()
            if distance is not None:
                print(f"[ULTRASCHALL] Gemessene Distanz: {distance} cm")
            else:
                print("[ULTRASCHALL] Keine gültige Messung")
            
            # Button-Check
            check_button()
            
            time.sleep(2)  # Alle 2 Sekunden messen
            
        except Exception as e:
            print(f"Fehler im Sensor-Thread: {e}")
            time.sleep(1)

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
    
    if video_filename and not video_filename.endswith('.mp4'):
        video_filename = video_filename + '.mp4'
    
    c.execute("""
        INSERT INTO events (timestamp, event_type, video_file)
        VALUES (?, ?, ?)
    """, (timestamp, event_type, video_filename))
    conn.commit()
    conn.close()
    print(f"Event hinzugefügt: {event_type} um {timestamp}")

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
    """API für die neuesten Events"""
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
    if not filename.endswith('.mp4'):
        filename = filename + '.mp4'
    
    return send_from_directory(VIDEO_DIR, filename)

@app.route("/test_sensors")
def test_sensors():
    """Test-Seite für Sensoren"""
    distance = get_distance()
    button_state = GPIO.input(BUTTON_PIN)
    
    html = f"""
    <html>
    <head>
        <title>Sensor Test</title>
        <meta http-equiv="refresh" content="2">
    </head>
    <body>
        <h1>Sensor Test</h1>
        <p><strong>Ultraschall Distanz:</strong> {distance or 'N/A'} cm</p>
        <p><strong>Button Status:</strong> {'GEDRÜCKT' if button_state == GPIO.LOW else 'NICHT GEDRÜCKT'}</p>
        <p><a href="/">Zurück zum Dashboard</a></p>
    </body>
    </html>
    """
    return html

@app.route("/manual_test")
def manual_test():
    """Manueller Test der Sensoren"""
    distance = get_distance()
    button_pressed = check_button()
    
    response = {
        "distance": distance,
        "button_pressed": button_pressed,
        "button_state": "GEDRÜCKT" if GPIO.input(BUTTON_PIN) == GPIO.LOW else "NICHT GEDRÜCKT"
    }
    
    return jsonify(response)

def cleanup():
    """Aufräumen bei Programmende"""
    global sensor_active
    sensor_active = False
    time.sleep(1)
    
    try:
        GPIO.cleanup()
        print("GPIO aufgeräumt")
    except:
        pass

if __name__ == "__main__":
    try:
        # Initialisiere Datenbank
        init_db()
        
        # Initialisiere GPIO
        init_gpio()
        
        # Sensor-Thread starten (inkl. Button-Check)
        sensor_thread = threading.Thread(target=sensor_thread, daemon=True)
        sensor_thread.start()
        
        print("\n" + "="*50)
        print("SMART DOORBELL SYSTEM GESTARTET")
        print("="*50)
        print("Dashboard: http://localhost:5000/")
        print("Sensor Test: http://localhost:5000/test_sensors")
        print("Manueller Test: http://localhost:5000/manual_test")
        print("\nÜberwachung aktiv:")
        print("- Button an GPIO26 (D2) - Drücke den Button")
        print("- Ultraschallsensor an GPIO13/6 (D7) - Misst alle 2 Sekunden")
        print("\nDrücke Strg+C zum Beenden")
        print("="*50 + "\n")
        
        # Flask App starten
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\n\nProgramm wird beendet...")
    except Exception as e:
        print(f"\nFehler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup()