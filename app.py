from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
import time
import subprocess
import os
import RPi.GPIO as GPIO
from pitop.pma import LED, Button, LightSensor

app = Flask(__name__)

# Pin-Definitionen für Pi-Top (BCM-Nummern!)
BUTTON_PIN = 26        # D2 = GPIO26 (BCM)
ULTRASONIC_TRIG = 14   # D7 = GPIO14 (BCM) für TRIG
ULTRASONIC_ECHO = 15   # D7 = GPIO15 (BCM) für ECHO
PIR_PIN = 7            # D4 = GPIO7 (BCM) für PIR Bewegungssensor
LED_PIN = 17           # D0 = GPIO17 (BCM) für LED

# Video-Aufnahme-Einstellungen
VIDEO_DURATION_BUTTON = 10  # 10 Sekunden Aufnahme bei Button
VIDEO_DURATION_MOTION = 5   # 5 Sekunden Aufnahme bei Motion
VIDEO_FPS = 30
VIDEO_RESOLUTION = "640x480"

# Motion-Einstellungen
MOTION_THRESHOLD = 30    # 30 Bewegungen
MOTION_TIMEFRAME = 3     # in 3 Sekunden

# Lichtsensor-Einstellungen
DARKNESS_THRESHOLD = 40  # Unter 40% = dunkel
LED_CHECK_INTERVAL = 2   # Alle 2 Sekunden prüfen

# Globale Variablen
sensor_active = True
last_button_state = True  # True = nicht gedrückt (wegen Pull-Up)
recording_active = False  # Verhindert mehrere gleichzeitige Aufnahmen
motion_times = []        # Zeitstempel für Bewegungen
led_on_dark = False      # Status der automatischen LED

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_doorbell.db"
VIDEO_DIR = BASE_DIR / "static" / "videos"

# Erstelle den Video-Ordner, falls nicht vorhanden
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Komponenten initialisieren
led = LED("D0")          # Pi-Top LED an D0
button = Button("D2")    # Pi-Top Button an D2
light_sensor = LightSensor("A0")  # Lichtsensor an A0

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
    
    if recording_active:
        print(f"[VIDEO] Bereits eine Aufnahme aktiv, überspringe...")
        return None
    
    recording_active = True
    
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
            '-framerate', '15',
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
            add_event(event_type, filename)
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
    """Thread für PIR-Bewegungssensor mit Cooldown und Entprellung"""
    print("Motion-Thread gestartet - Überwache Bewegungen")
    
    # PIR Sensor kalibrieren
    print("PIR Sensor kalibriert sich... 15 Sekunden")
    for i in range(15, 0, -1):
        print(f"  Kalibrierung: {i} Sekunden...", end='\r')
        time.sleep(1)
    print("  Kalibrierung: Fertig!            ")
    print("PIR Sensor bereit!")
    
    # Variablen für Cooldown und Entprellung
    cooldown_until = 0
    last_motion_time = 0
    motion_count = 0
    
    while sensor_active:
        try:
            now = time.time()
            
            # Cooldown: Nach erkannter Bewegung 2 Sekunden Pause
            if now < cooldown_until:
                time.sleep(0.05)
                continue
            
            if GPIO.input(PIR_PIN):
                # Bewegung erkannt
                current_time = now
                
                # Entprellung: Mindestens 0.5 Sekunden seit letzter Bewegung
                if current_time - last_motion_time > 0.5:
                    motion_times.append(current_time)
                    print(f"\n[🏃 MOTION] Bewegung erkannt um {current_time:.0f}")
                    
                    # Cooldown für 2 Sekunden setzen
                    cooldown_until = current_time + 2
                    last_motion_time = current_time
                    motion_count += 1
                    
                    # Alte Einträge entfernen
                    global motion_times
                    motion_times = [t for t in motion_times if current_time - t <= MOTION_TIMEFRAME]
                    
                    print(f"  Bewegungen in letzten {MOTION_TIMEFRAME}s: {len(motion_times)}/{MOTION_THRESHOLD}")
                    
                    # Prüfen ob Schwellwert erreicht
                    if len(motion_times) >= MOTION_THRESHOLD:
                        print(f"  ⚠️  SCHWELLE ERREICHT! Starte {VIDEO_DURATION_MOTION}s Videoaufnahme")
                        
                        video_thread = threading.Thread(
                            target=record_video,
                            args=("motion", VIDEO_DURATION_MOTION),
                            daemon=True
                        )
                        video_thread.start()
                        motion_times = []  # Reset nach Auslösung
                        motion_count = 0
                        # Extra langer Cooldown nach Video
                        cooldown_until = current_time + 5
            
            time.sleep(0.05)  # 50ms Abtastrate
            
        except Exception as e:
            print(f"Fehler im Motion-Thread: {e}")
            time.sleep(0.5)

def check_light():
    """Prüft Lichtsensor und steuert LED bei Dunkelheit"""
    global led_on_dark
    
    try:
        light_value = light_sensor.reading
        
        if light_value < DARKNESS_THRESHOLD and not led_on_dark:
            # Es ist dunkel - LED einschalten
            led.on()
            led_on_dark = True
            print(f"[💡 LICHT] Dunkel erkannt ({light_value:.0f}%) - LED EIN")
            
        elif light_value >= DARKNESS_THRESHOLD and led_on_dark:
            # Es ist hell - LED ausschalten
            led.off()
            led_on_dark = False
            print(f"[💡 LICHT] Hell erkannt ({light_value:.0f}%) - LED AUS")
            
    except Exception as e:
        print(f"Fehler bei Lichtsensor: {e}")

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

def motion_thread():
    """Thread für PIR-Bewegungssensor"""
    print("Motion-Thread gestartet - Überwache Bewegungen")
    
    # PIR Sensor kalibrieren
    print("PIR Sensor kalibriert sich... 10 Sekunden")
    time.sleep(10)
    print("PIR Sensor bereit!")
    
    while sensor_active:
        try:
            check_motion()
            time.sleep(0.05)  # 50ms Abtastrate
            
        except Exception as e:
            print(f"Fehler im Motion-Thread: {e}")
            time.sleep(0.1)

def light_thread():
    """Thread für Lichtsensor und LED-Steuerung"""
    print("Light-Thread gestartet - Überwache Helligkeit")
    print(f"LED schaltet bei < {DARKNESS_THRESHOLD}% Helligkeit")
    
    while sensor_active:
        try:
            check_light()
            time.sleep(LED_CHECK_INTERVAL)
            
        except Exception as e:
            print(f"Fehler im Light-Thread: {e}")
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
    print(f"[📀 DATENBANK] Event hinzugefügt: {event_type} um {timestamp}")

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
    
    c.execute("SELECT COUNT(*) FROM events")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'ring'")
    rings = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM events WHERE event_type = 'motion'")
    motions = c.fetchone()[0]
    
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
    events = get_events(limit=20)
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
    motion_state = GPIO.input(PIR_PIN)
    light_value = light_sensor.reading
    
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
            <p>Bewegungen (letzte {MOTION_TIMEFRAME}s): <strong>{len(motion_times)}/{MOTION_THRESHOLD}</strong></p>
        </div>
        <div class="sensor">
            <h3>💡 Lichtsensor</h3>
            <p>Helligkeit: <strong>{light_value:.1f}%</strong></p>
            <p>LED (Auto): <strong>{'EIN' if led_on_dark else 'AUS'}</strong></p>
            <p>Schwelle: {DARKNESS_THRESHOLD}%</p>
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
        led.off()
        GPIO.cleanup()
        print("GPIO aufgeräumt")
    except:
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
            threading.Thread(target=light_thread, daemon=True)
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
        print(f"  • Lichtsensor (A0)  → LED automatisch bei < {DARKNESS_THRESHOLD}%")
        print(f"  • Ultraschall (D7)  → Distanzmessung alle 2s")
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