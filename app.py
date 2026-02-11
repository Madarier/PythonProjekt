from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
import time
import subprocess
import os
import RPi.GPIO as GPIO

app = Flask(__name__)

# Pin-Definitionen für Pi-Top (BCM-Nummern!)
BUTTON_PIN = 26        # D2 = GPIO26 (BCM)
ULTRASONIC_TRIG = 14   # D7 = GPIO14 (BCM) für TRIG
ULTRASONIC_ECHO = 15   # D7 = GPIO15 (BCM) für ECHO

# Video-Aufnahme-Einstellungen
VIDEO_DURATION = 5     # 5 Sekunden Aufnahme
VIDEO_FPS = 30         # 15 FPS für kleinere Dateien
VIDEO_RESOLUTION = "640x480"  # Auflösung

# Globale Variablen
sensor_active = True
last_button_state = True  # True = nicht gedrückt (wegen Pull-Up)
recording_active = False  # Verhindert mehrere gleichzeitige Aufnahmen

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

def record_video():
    """Nimmt ein 5-Sekunden Video mit der USB-Webcam auf"""
    global recording_active
    
    if recording_active:
        print("[VIDEO] Bereits eine Aufnahme aktiv, überspringe...")
        return None
    
    recording_active = True
    
    try:
        # Generiere Dateinamen
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d")
        time_str = timestamp.strftime("%H%M%S")
        filename = f"button_{date_str}{time_str}.mp4"
        video_path = VIDEO_DIR / filename
        
        print(f"[VIDEO] Starte Videoaufnahme: {filename}")
        
        # ffmpeg Befehl für Videoaufnahme
        # -t 5: 5 Sekunden Aufnahme
        # -s 640x480: Auflösung
        # -r 15: 15 FPS
        # -f v4l2: Video4Linux2 Treiber für USB-Kamera
        # /dev/video0: Standard-Webcam Device
        
        cmd = [
            'ffmpeg',
            '-f', 'v4l2',          # Video4Linux2 Input Format
            '-framerate', '15',    # 15 FPS
            '-video_size', '640x480',  # Auflösung
            '-i', '/dev/video0',   # Webcam Device
            '-t', '5',             # 5 Sekunden Aufnahme
            '-vf', 'format=yuv420p',  # Farbformat
            '-c:v', 'libx264',     # H.264 Codec
            '-preset', 'ultrafast', # Schnelle Kodierung
            '-y',                  # Überschreiben ohne Nachfrage
            str(video_path)
        ]
        
        # Führe ffmpeg aus
        process = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=10  # Timeout nach 10 Sekunden
        )
        
        if process.returncode == 0:
            print(f"[VIDEO] Aufnahme erfolgreich gespeichert: {filename}")
            
            # Event in Datenbank speichern
            add_event("ring", filename)
            
            return filename
        else:
            print(f"[VIDEO] Fehler bei Aufnahme: {process.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        print("[VIDEO] Aufnahme-Timeout - Prozess wurde beendet")
        return None
    except Exception as e:
        print(f"[VIDEO] Fehler bei Videoaufnahme: {e}")
        return None
    finally:
        recording_active = False

def button_thread():
    """Separater Thread für Button-Überwachung"""
    global last_button_state
    
    print("Button-Thread gestartet - Sofortige Reaktion")
    
    while sensor_active:
        try:
            current_state = GPIO.input(BUTTON_PIN)
            
            # Button wurde gedrückt (von HIGH auf LOW)
            if last_button_state == True and current_state == False:
                print(f"[BUTTON] Button an GPIO{BUTTON_PIN} wurde betätigt!")
                
                # Starte Videoaufnahme in einem separaten Thread
                video_thread = threading.Thread(target=record_video, daemon=True)
                video_thread.start()
            
            # Button wurde losgelassen (von LOW auf HIGH)
            elif last_button_state == False and current_state == True:
                print(f"[BUTTON] Button an GPIO{BUTTON_PIN} wurde losgelassen!")
            
            last_button_state = current_state
            
            # Sehr kurze Pause für schnelle Reaktion
            time.sleep(0.05)  # 50ms - sehr schnell
            
        except Exception as e:
            print(f"Fehler im Button-Thread: {e}")
            time.sleep(0.1)

def ultrasonic_thread():
    """Thread für regelmäßige Ultraschall-Messungen"""
    print("Ultraschall-Thread gestartet - Messung alle 2 Sekunden")
    
    while sensor_active:
        try:
            distance = get_distance()
            if distance is not None:
                print(f"[ULTRASCHALL] Gemessene Distanz: {distance} cm")
            else:
                print("[ULTRASCHALL] Keine gültige Messung")
            
            time.sleep(2)  # Alle 2 Sekunden messen
            
        except Exception as e:
            print(f"Fehler im Ultraschall-Thread: {e}")
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
    print(f"[DATENBANK] Event hinzugefügt: {event_type} um {timestamp}, Video: {video_filename}")

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

@app.route("/test_video")
def test_video():
    """Manuelle Testseite für Videoaufnahme"""
    html = """
    <html>
    <head>
        <title>Video Test</title>
    </head>
    <body>
        <h1>Video Test</h1>
        <form action="/record_video" method="get">
            <button type="submit">Manuell 5s Video aufnehmen</button>
        </form>
        <p><a href="/">Zurück zum Dashboard</a></p>
    </body>
    </html>
    """
    return html

@app.route("/record_video")
def manual_record_video():
    """Manuelle Videoaufnahme starten"""
    result = record_video()
    
    if result:
        return jsonify({
            "status": "success", 
            "message": f"Videoaufnahme gestartet: {result}",
            "filename": result
        })
    else:
        return jsonify({
            "status": "error", 
            "message": "Videoaufnahme fehlgeschlagen"
        }), 500

@app.route("/check_webcam")
def check_webcam():
    """Prüft ob die Webcam verfügbar ist"""
    try:
        # Prüfe ob /dev/video0 existiert
        if os.path.exists('/dev/video0'):
            # Versuche Video-Informationen zu bekommen
            cmd = ['v4l2-ctl', '--device=/dev/video0', '--list-formats']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            return jsonify({
                "status": "available",
                "device": "/dev/video0",
                "formats": result.stdout if result.returncode == 0 else "Unknown"
            })
        else:
            return jsonify({
                "status": "not_found",
                "message": "Webcam /dev/video0 nicht gefunden"
            }), 404
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def cleanup():
    """Aufräumen bei Programmende"""
    global sensor_active
    sensor_active = False
    time.sleep(2)  # Warte auf Threads
    
    try:
        GPIO.cleanup()
        print("GPIO aufgeräumt")
    except:
        pass

if __name__ == "__main__":
    try:
        # Prüfe ob ffmpeg installiert ist
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True)
            print("ffmpeg gefunden - Videoaufnahme möglich")
        except FileNotFoundError:
            print("WARNUNG: ffmpeg nicht installiert. Videoaufnahme nicht möglich.")
            print("Installiere mit: sudo apt install ffmpeg")
        
        # Prüfe Webcam
        print("\nPrüfe Webcam...")
        if os.path.exists('/dev/video0'):
            print("Webcam /dev/video0 gefunden")
        else:
            print("WARNUNG: Webcam /dev/video0 nicht gefunden!")
            print("Stelle sicher, dass die USB-Webcam angeschlossen ist.")
        
        # Initialisiere Datenbank
        init_db()
        
        # Initialisiere GPIO
        init_gpio()
        
        # Zwei separate Threads starten
        button_thread_obj = threading.Thread(target=button_thread, daemon=True)
        ultrasonic_thread_obj = threading.Thread(target=ultrasonic_thread, daemon=True)
        
        button_thread_obj.start()
        ultrasonic_thread_obj.start()
        
        print("\n" + "="*60)
        print("SMART DOORBELL SYSTEM GESTARTET")
        print("="*60)
        print("Dashboard: http://localhost:5000/")
        print("Sensor Test: http://localhost:5000/test_sensors")
        print("Video Test: http://localhost:5000/test_video")
        print("Webcam Check: http://localhost:5000/check_webcam")
        print("\nÜberwachung aktiv:")
        print(f"- Button an GPIO{BUTTON_PIN} (D2) - Startet 5s Videoaufnahme")
        print(f"- Ultraschallsensor an GPIO{ULTRASONIC_TRIG}/{ULTRASONIC_ECHO} (D7)")
        print("\nVideo-Einstellungen:")
        print(f"- Dauer: {VIDEO_DURATION} Sekunden")
        print(f"- Auflösung: {VIDEO_RESOLUTION}")
        print(f"- FPS: {VIDEO_FPS}")
        print("\nDrücke Strg+C zum Beenden")
        print("="*60 + "\n")
        
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