#!/usr/bin/env python3
from pitop.pma import LED, Button, MotionSensor
from time import sleep, time
from threading import Thread

# Komponenten initialisieren
led = LED("D0")           # LED an D0
button = Button("D2")     # Button an D2
motion = MotionSensor("D4") # Bewegungssensor an D4

# Globale Variablen
motion_times = []
led_active = False

print("=" * 60)
print("🎛️  PI-TOP BUTTON & MOTION TEST")
print("=" * 60)
print("LED an D0")
print("Button an D2")
print("Motion Sensor an D4")
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

def motion_detected():
    """Callback für Bewegung"""
    global motion_times
    
    now = time()
    motion_times.append(now)
    print(f"\n[🏃 MOTION] Bewegung erkannt um {now:.0f}")
    
    # Alte Einträge entfernen (>6 Sekunden)
    motion_times = [t for t in motion_times if now - t <= 6]
    
    # Prüfen ob 10 Bewegungen in den letzten 6 Sekunden
    if len(motion_times) >= 10:
        print(f"  ⚠️  {len(motion_times)} Bewegungen in 6s! LED aktivieren")
        Thread(target=led_control).start()
        motion_times = []  # Reset nach Auslösung

# Event-Handler registrieren
button.when_pressed = button_pressed
motion.when_motion_detected = motion_detected

# Hauptprogramm läuft im Hintergrund
try:
    while True:
        sleep(0.1)
        
except KeyboardInterrupt:
    print("\n\n" + "=" * 60)
    print("✅ TEST BEENDET")
    print("=" * 60)
    led.off()