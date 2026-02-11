#!/usr/bin/env python3
import time
import RPi.GPIO as GPIO
from pitop import Pitop
from pitop.pma import AnalogSensor, LightSensor

# Initialisiere Pi-Top
pitop = Pitop()

# Option 1: Mit LightSensor Klasse (empfohlen)
# Der Pi-Top hat spezielle Sensorklassen
try:
    light = LightSensor("A0")  # Direkt an A0
    print("LightSensor erfolgreich initialisiert")
except:
    print("LightSensor nicht verfügbar, verwende AnalogSensor...")
    # Option 2: Mit AnalogSensor Klasse
    light = AnalogSensor("A0")  # Allgemeiner analoger Sensor

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

print("=" * 60)
print("PI-TOP LICHTSENSOR TEST (A0)")
print("=" * 60)
print("Sensor an A0 (P1/P0) angeschlossen")
print("\nDrücke Strg+C zum Beenden")
print("-" * 60)

def read_light():
    """Liest den aktuellen Lichtwert vom A0"""
    try:
        # Verschiedene Methoden je nach verfügbarer Klasse
        if hasattr(light, 'reading'):
            value = light.reading  # LightSensor
        elif hasattr(light, 'value'):
            value = light.value    # AnalogSensor
        else:
            value = light.read()   # Fallback
            
        # Wert normalisieren (0-100%)
        if value > 100:  # Wahrscheinlich 0-1023 oder 0-255
            percentage = min(100, value / 1023 * 100)
            normalized = value
        else:  # Bereits 0-100
            percentage = value
            normalized = value * 10.23
            
        return normalized, percentage
    except Exception as e:
        print(f"Fehler beim Lesen: {e}")
        return None, None

try:
    # Erstes paar Messungen für Kalibrierung
    print("Kalibriere Sensor... bitte 2 Sekunden warten")
    time.sleep(2)
    
    # Speichere Minimal- und Maximalwerte
    min_value = 1000
    max_value = 0
    samples = []
    
    print("\nStarte Messung alle 0.5 Sekunden:")
    print("-" * 60)
    
    while True:
        raw_value, percentage = read_light()
        
        if raw_value is not None:
            # Aktualisiere Min/Max
            min_value = min(min_value, raw_value)
            max_value = max(max_value, raw_value)
            
            samples.append(percentage)
            if len(samples) > 10:
                samples.pop(0)
            avg_percentage = sum(samples) / len(samples)
            
            # Lichtstärke als Balken visualisieren
            bar_length = int(percentage / 5)  # 20 Balken = 100%
            bar = "█" * bar_length + "░" * (20 - bar_length)
            
            # Zeitstempel
            timestamp = time.strftime("%H:%M:%S")
            
            # Lichtstatus bestimmen
            if percentage < 10:
                status = "🌑 SEHR DUNKEL"
            elif percentage < 25:
                status = "🌙 DUNKEL"
            elif percentage < 50:
                status = "⛅ NORMAL"
            elif percentage < 75:
                status = "☀️ HELL"
            else:
                status = "🔥 SEHR HELL"
            
            # Ausgabe
            print(f"[{timestamp}] {status}")
            print(f"  Wert: {raw_value:3.0f} | {percentage:5.1f}%")
            print(f"  [{bar}]")
            print(f"  Min: {min_value:3.0f} | Max: {max_value:3.0f} | Avg: {avg_percentage:3.0f}%")
            print()
        
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nTest beendet.")
    print(f"\nStatistik während der Messung:")
    print(f"  Minimalwert: {min_value:.0f}")
    print(f"  Maximalwert: {max_value:.0f}")
    print(f"  Dynamikumfang: {max_value - min_value:.0f}")

except Exception as e:
    print(f"\nFehler: {e}")

finally:
    GPIO.cleanup()
    print("GPIO aufgeräumt")