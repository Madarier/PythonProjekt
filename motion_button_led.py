#!/usr/bin/env python3
from pitop.pma import LED, Button
import RPi.GPIO as GPIO
from time import sleep, time
from threading import Thread

# GPIO Modus setzen
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin-Definitionen
LED_PIN = 17           # D0 = GPIO17
BUTTON_PIN = 26        # D2 = GPIO26
PIR_PIN = 7            # D4 = GPIO8 (probier 8 oder 7)

# Komponenten initialisieren
led = LED("D0")        # Pi-Top LED an D0
button = Button("D2")  # Pi-Top Button an D2

# GPIO für PIR einrichten
GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Globale Variablen
motion_times = []
led_active = False

print("=" * 60)
print("🎛️  PI-TOP BUTTON & PIR MOTION TEST")
print("=" * 60)
print(f"LED an D0 (GPIO17)")
print(f"Button an D2 (GPIO26)")
print(f"PIR Motion an D4 (GPIO{PIR_PIN})")
print("\n📋 Aktionen:")
print("   • Button drücken → LED 2s an")
print("   • 10x Bewegung in 6s → LED 2s an")
print("\nDrücke Strg+C zum Beenden")
print("-" * 60)

def led_control():
    """Schaltet LED für 2 Sekunden ein"""
    global led_active
    if not led_active:
        led_active = True
        led.on()
        print(f"  🔦 LED EIN - {time():.0f}")
        sleep(2)
        led.off()
        print(f"  🔦 LED AUS - {time():.0f}")
        led_active = False

def button_pressed():
    """Callback für Button"""
    print(f"\n[🟢 BUTTON] Gedrückt um {time():.0f}")
    Thread(target=led_control).start()

def check_motion():
    """Prüft PIR-Sensor auf Bewegung"""
    global motion_times
    
    now = time()
    
    if GPIO.input(PIR_PIN):
        motion_times.append(now)
        print(f"\n[🏃 MOTION] Bewegung erkannt um {now:.0f}")
        
        # Alte Einträge entfernen (>6 Sekunden)
        motion_times = [t for t in motion_times if now - t <= 6]
        
        # Prüfen ob 10 Bewegungen in den letzten 6 Sekunden
        if len(motion_times) >= 10:
            print(f"  ⚠️  {len(motion_times)} Bewegungen in 6s! LED aktivieren")
            Thread(target=led_control).start()
            motion_times = []  # Reset nach Auslösung

# Button Event-Handler
button.when_pressed = button_pressed

print("PIR Sensor kalibriert sich... 10 Sekunden warten")
sleep(10)
print("Bereit! Warte auf Bewegungen...\n")

try:
    while True:
        check_motion()
        sleep(0.05)  # 50ms Abtastrate
        
except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print("✅ TEST BEENDET")
    print("=" * 60)
    led.off()
    GPIO.cleanup()