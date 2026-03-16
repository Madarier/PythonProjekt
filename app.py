from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
import time
import subprocess
import os
import math
import RPi.GPIO as GPIO
from pitop.pma import Button, Potentiometer, LED

app = Flask(__name__)

# Pin-Definitionen für Pi-Top (BCM-Nummern!)
BUTTON_PIN = 26        # D2 = GPIO26 (BCM)
ULTRASONIC_TRIG = 14   # D7 = GPIO14 (BCM) für TRIG
ULTRASONIC_ECHO = 15   # D7 = GPIO15 (BCM) für ECHO
PIR_PIN = 7            # D4 = GPIO7 (BCM) für PIR Bewegungssensor
# Video-Aufnahme-Einstellungen
VIDEO_DURATION_BUTTON = 10  # 10 Sekunden Aufnahme bei Button
VIDEO_DURATION_MOTION = 5   # 5 Sekunden Aufnahme bei Motion
VIDEO_FPS = 30
VIDEO_RESOLUTION = "640x480"

# Motion-Einstellungen
MOTION_THRESHOLD = 3     # 3 Bewegungen
MOTION_TIMEFRAME = 30    # in 30 Sekunden
MOTION_COOLDOWN = 5      # 5 Sekunden Pause nach jeder Erkennung

# Temperatur-Einstellungen (Grove Temperature Sensor v1.2)
TEMP_B = 4275       # B-Wert des NTC Thermistors
TEMP_R0 = 100000    # Widerstand bei 25°C (100K Ohm)

# Globale Variablen
sensor_active = True
last_button_state = True  # True = nicht gedrückt (wegen Pull-Up)
recording_active = False  # Verhindert mehrere gleichzeitige Aufnahmen
motion_times = []        # Zeitstempel für Bewegungen
state_lock = threading.Lock()  # Lock für Thread-sichere Zugriffe

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"
VIDEO_DIR = BASE_DIR / "static" / "videos"

# Erstelle den Video-Ordner, falls nicht vorhanden
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Komponenten initialisieren
button = Button("D2")        # Pi-Top Button an D2
temp_sensor = Potentiometer("A0")  # Grove Temperature Sensor an A0
recording_led = LED("D0")    # LED an D0 - leuchtet während Aufnahme

def init_gpio():
    """Initialisiert die GPIO-Pins für Pi-Top"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Button mit Pull-Up Widerstand (D2)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Ultraschallsensor (D7)
        GPIO.setup(ULTRASONIC_TRIG, GPIO.OUT)
        GPIO.setup(ULTRASONIC_ECHO, GPIO.IN)
        GPIO.output(ULTRASONIC_TRIG, False)
        
        # PIR Bewegungssensor (D4)
        GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        
        time.sleep(0.5)
        
        print("GPIO für Pi-Top initialisiert")
        print(f"Button an GPIO{BUTTON_PIN} (D2)")
        print(f"Ultraschall TRIG an GPIO{ULTRASONIC_TRIG} (D7)")
        print(f"Ultraschall ECHO an GPIO{ULTRASONIC_ECHO} (D7)")
        print(f"PIR Motion an GPIO{PIR_PIN} (D4)")
        
    except Exception as e:
        print(f"Fehler bei GPIO-Initialisierung: {e}")
        raise

def get_temperature():
    """Liest die Temperatur vom Grove Temperature Sensor v1.2"""
    try:
        analog_value = temp_sensor.position  # 0.0 bis 1.0
        if analog_value <= 0 or analog_value >= 1:
            return None
        R = TEMP_R0 * (1.0 / analog_value - 1.0)
        temperature = 1.0 / (math.log(R / TEMP_R0) / TEMP_B + 1.0 / 298.15) - 273.15
        return round(temperature, 1)
    except Exception as e:
        print(f"Fehler bei Temperaturmessung: {e}")
        return None

def get_distance():
    """Misst die Distanz mit dem Ultraschallsensor"""
    try:
        GPIO.output(ULTRASONIC_TRIG, True)
        time.sleep(0.00001)
        GPIO.output(ULTRASONIC_TRIG, False)
        
        pulse_start = time.time()
        pulse_end = time.time()
        
        timeout_start = time.time()
        while GPIO.input(ULTRASONIC_ECHO) == 0:
            pulse_start = time.time()
            if time.time() - timeout_start > 0.1:
                return None
        
        timeout_start = time.time()
        while GPIO.input(ULTRASONIC_ECHO) == 1:
            pulse_end = time.time()
            if time.time() - timeout_start > 0.1:
                return None
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)
        
        if 2 < distance < 400:
            return distance
        else:
            return None
            
    except Exception as e:
        print(f"Fehler bei Distanzmessung: {e}")
        return None

def record_video(event_type, duration):
    """Nimmt ein Video mit der USB-Webcam auf"""
    global recording_active

    with state_lock:
        if recording_active:
            print(f"[VIDEO] Bereits eine Aufnahme aktiv, überspringe...")
            return None
        recording_active = True

    recording_led.on()

    try:
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y%m%d")
        time_str = timestamp.strftime("%H%M%S")
        filename = f"{event_type}_{date_str}{time_str}.mp4"
        video_path = VIDEO_DIR / filename
        
        print(f"[VIDEO] Starte {duration}s Videoaufnahme: {filename}")
        
        cmd = [
            'ffmpeg',
            '-f', 'v4l2',
            '-framerate', str(VIDEO_FPS),
            '-video_size', VIDEO_RESOLUTION,
            '-i', '/dev/video0',
            '-t', str(duration),
            '-vf', 'format=yuv420p',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-y',
            str(video_path)
        ]
        
        process = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=duration + 5
        )
        
        if process.returncode == 0:
            print(f"[VIDEO] Aufnahme erfolgreich gespeichert: {filename}")
            temperature = get_temperature()
            add_event(event_type, filename, temperature)
            return filename
        else:
            print(f"[VIDEO] Fehler bei Aufnahme: {process.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        print("[VIDEO] Aufnahme-Timeout")
        return None
    except Exception as e:
        print(f"[VIDEO] Fehler: {e}")
        return None
    finally:
        recording_led.off()
        recording_active = False

def button_pressed():
    """Callback für Button-Druck"""
    print(f"\n[🔔 BUTTON] Button an GPIO{BUTTON_PIN} wurde betätigt!")
    
    # Videoaufnahme starten (10 Sekunden)
    video_thread = threading.Thread(
        target=record_video, 
        args=("ring", VIDEO_DURATION_BUTTON), 
        daemon=True
    )
    video_thread.start()

def motion_thread():
    """Thread für PIR-Bewegungssensor - NUR bei Zustandsänderung"""
    global motion_times

    print("Motion-Thread gestartet - Überwache Bewegungen")

    # WICHTIG: PIR Sensor braucht Zeit zum Kalibrieren!
    print("PIR Sensor kalibriert sich... 20 Sekunden warten")
    for i in range(20, 0, -1):
        print(f"  Kalibrierung: {i} Sekunden...", end='\r')
        time.sleep(1)
    print("  Kalibrierung: Fertig!            ")
    print("PIR Sensor bereit - Reagiere NUR auf Zustandsänderungen")

    # Variablen für Zustandsänderung und Cooldown
    last_state = False
    cooldown_until = 0
    motion_count_total = 0

    while sensor_active:
        try:
            now = time.time()
            current_state = GPIO.input(PIR_PIN)

            # Cooldown: Nach erkannter Bewegung 2 Sekunden Pause
            if now < cooldown_until:
                time.sleep(0.05)
                continue

            # NUR bei WECHSEL von LOW zu HIGH (steigende Flanke)
            if current_state == True and last_state == False:
                motion_count_total += 1

                with state_lock:
                    motion_times.append(now)
                    # Alte Bewegungen entfernen (> MOTION_TIMEFRAME Sekunden)
                    motion_times = [t for t in motion_times if now - t <= MOTION_TIMEFRAME]
                    current_count = len(motion_times)

                print(f"\n[🏃 MOTION] Bewegung #{motion_count_total} um {now:.0f}")

                # Cooldown setzen - verhindert Dauerfeuer
                cooldown_until = now + MOTION_COOLDOWN

                print(f"  Bewegungen in letzten {MOTION_TIMEFRAME}s: {current_count}/{MOTION_THRESHOLD}")

                # Prüfen ob Schwellwert erreicht
                if current_count >= MOTION_THRESHOLD:
                    print(f"  ⚠️  SCHWELLE ERREICHT! Starte {VIDEO_DURATION_MOTION}s Videoaufnahme")

                    video_thread = threading.Thread(
                        target=record_video,
                        args=("motion", VIDEO_DURATION_MOTION),
                        daemon=True
                    )
                    video_thread.start()

                    # Reset nach erfolgreicher Auslösung
                    with state_lock:
                        motion_times = []
                    motion_count_total = 0

                    # Extra langer Cooldown nach Video (8 Sekunden)
                    cooldown_until = now + 8

            # Aktuellen Zustand für nächsten Durchlauf speichern
            last_state = current_state
            time.sleep(0.05)  # 50ms Abtastrate

        except Exception as e:
            print(f"Fehler im Motion-Thread: {e}")
            time.sleep(0.5)

def button_thread():
    """Separater Thread für Button-Überwachung"""
    global last_button_state
    
    print("Button-Thread gestartet - Sofortige Reaktion")
    
    while sensor_active:
        try:
            current_state = GPIO.input(BUTTON_PIN)
            
            if last_button_state == True and current_state == False:
                button_pressed()
            
            last_button_state = current_state
            time.sleep(0.05)
            
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
                print(f"[📏 ULTRASCHALL] Distanz: {distance} cm")
            time.sleep(2)
            
        except Exception as e:
            print(f"Fehler im Ultraschall-Thread: {e}")
            time.sleep(1)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                video_file TEXT,
                temperature REAL
            )
        """)
        # Migration: Spalte hinzufügen falls sie in alter DB fehlt
        try:
            c.execute("ALTER TABLE events ADD COLUMN temperature REAL")
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits
        conn.commit()
    finally:
        conn.close()

def add_event(event_type, video_filename=None, temperature=None):
    """Fügt einen neuen Event-Eintrag in die Datenbank hinzu"""
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if video_filename and not video_filename.endswith('.mp4'):
            video_filename = video_filename + '.mp4'

        c.execute("""
            INSERT INTO events (timestamp, event_type, video_file, temperature)
            VALUES (?, ?, ?, ?)
        """, (timestamp, event_type, video_filename, temperature))
        conn.commit()
        print(f"[📀 DATENBANK] Event hinzugefügt: {event_type} um {timestamp} ({temperature}°C)")
    finally:
        conn.close()

def get_events(limit=None):
    """Holt Events aus der Datenbank"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if limit:
            c.execute("""
                SELECT id, timestamp, event_type, video_file, temperature
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        else:
            c.execute("""
                SELECT id, timestamp, event_type, video_file, temperature
                FROM events
                ORDER BY timestamp DESC
            """)

        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_event_by_id(event_id):
    """Holt ein spezifisches Event anhand der ID"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT id, timestamp, event_type, video_file, temperature
            FROM events
            WHERE id = ?
        """, (event_id,))

        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_event_stats():
    """Gibt Statistiken über die Events zurück"""
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM events")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'ring'")
        rings = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'motion'")
        motions = c.fetchone()[0]

        c.execute("SELECT timestamp FROM events ORDER BY timestamp DESC LIMIT 1")
        last_event = c.fetchone()
        last_timestamp = last_event[0] if last_event else "Keine Events"

        return {
            'total': total,
            'rings': rings,
            'motions': motions,
            'last_event': last_timestamp
        }
    finally:
        conn.close()

@app.route("/")
def dashboard():
    """Haupt-Dashboard mit Event-Buttons"""
    events = get_events(limit=20)
    stats = get_event_stats()
    temperature = get_temperature()
    return render_template("dashboard.html", events=events, stats=stats, temperature=temperature)

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
            safe_type = secure_filename(event_type) or "unknown"
            video_filename = f"{safe_type}_{timestamp}.mp4"
            video_path = VIDEO_DIR / video_filename
            video_file.save(video_path)
    
    temperature = get_temperature()
    add_event(event_type, video_filename, temperature)
    return jsonify({"status": "success", "video_filename": video_filename, "temperature": temperature})

@app.route("/test_sensors")
def test_sensors():
    """Test-Seite für Sensoren"""
    distance = get_distance()
    button_state = GPIO.input(BUTTON_PIN)
    motion_state = GPIO.input(PIR_PIN)
    temperature = get_temperature()

    with state_lock:
        motion_count = len(motion_times)

    temp_display = f"{temperature}°C" if temperature is not None else "N/A"

    html = f"""
    <html>
    <head>
        <title>Sensor Test</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body {{ font-family: Arial; padding: 20px; }}
            .sensor {{ background: #f0f0f0; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .green {{ color: green; }}
            .red {{ color: red; }}
        </style>
    </head>
    <body>
        <h1>🔍 Sensor Test</h1>
        <div class="sensor">
            <h3>🌡️ Temperatur</h3>
            <p>Aktuell: <strong>{temp_display}</strong></p>
        </div>
        <div class="sensor">
            <h3>📏 Ultraschall</h3>
            <p>Distanz: <strong>{distance or 'N/A'}</strong> cm</p>
        </div>
        <div class="sensor">
            <h3>🟢 Button</h3>
            <p>Status: <strong class="{'red' if button_state == GPIO.LOW else 'green'}">
                {'GEDRÜCKT' if button_state == GPIO.LOW else 'NICHT GEDRÜCKT'}</strong></p>
        </div>
        <div class="sensor">
            <h3>🏃 PIR Motion</h3>
            <p>Status: <strong class="{'red' if motion_state else 'green'}">
                {'BEWEGUNG' if motion_state else 'KEINE'}</strong></p>
            <p>Bewegungen (letzte {MOTION_TIMEFRAME}s): <strong>{motion_count}/{MOTION_THRESHOLD}</strong></p>
        </div>
        <p><a href="/">⬅ Zurück zum Dashboard</a></p>
    </body>
    </html>
    """
    return html

def cleanup():
    """Aufräumen bei Programmende"""
    global sensor_active
    sensor_active = False
    time.sleep(2)
    
    try:
        recording_led.off()
        GPIO.cleanup()
        print("GPIO aufgeräumt")
    except Exception:
        pass

if __name__ == "__main__":
    try:
        # Prüfe ffmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True)
            print("✓ ffmpeg gefunden")
        except FileNotFoundError:
            print("⚠️ ffmpeg nicht installiert!")
            print("   Installiere: sudo apt install ffmpeg")
        
        # Prüfe Webcam
        if os.path.exists('/dev/video0'):
            print("✓ Webcam gefunden")
        else:
            print("⚠️ Keine Webcam unter /dev/video0 gefunden!")
        
        # Initialisiere
        init_db()
        init_gpio()
        
        # Threads starten
        threads = [
            threading.Thread(target=button_thread, daemon=True),
            threading.Thread(target=ultrasonic_thread, daemon=True),
            threading.Thread(target=motion_thread, daemon=True),
        ]
        
        for t in threads:
            t.start()
        
        print("\n" + "="*70)
        print("🏠 SMART DOORBELL SYSTEM - ALL SENSORS ACTIVE")
        print("="*70)
        print("📊 Dashboard: http://localhost:5000/")
        print("🔍 Sensor Test: http://localhost:5000/test_sensors")
        print("\n🎯 AKTIONEN:")
        print(f"  • Button (D2)       → 10s Video (ring event)")
        print(f"  • PIR Motion (D4)   → {MOTION_THRESHOLD}x in {MOTION_TIMEFRAME}s → 5s Video (motion event)")
        print(f"  • Ultraschall (D7)  → Distanzmessung alle 2s")
        print(f"  • Temperatur (A0)   → Grove Temperature Sensor v1.2")
        print("\n" + "="*70)
        print("Drücke Strg+C zum Beenden")
        print("="*70 + "\n")
        
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\n\nProgramm wird beendet...")
    except Exception as e:
        print(f"\nFehler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup()