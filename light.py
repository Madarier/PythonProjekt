#!/usr/bin/env python3
import time
import RPi.GPIO as GPIO
from pitop import Pitop
from pitop.labs import ADCDevice

# Initialisiere Pi-Top
pitop = Pitop()

# ADC initialisieren (für analoge Eingänge)
# Der Pi-Top hat intern einen ADS7830 oder ähnlichen ADC
adc = ADCDevice()

# Sensor an A0 angeschlossen
# A0 = P1/P0 = Kanal 0 des ADC
LIGHT_SENSOR_PIN = 0  # Kanal 0 für A0

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
        # Analogwert lesen (0-255 bei 8-bit ADC)
        value = adc.analog_read(LIGHT_SENSOR_PIN)
        
        # In Spannung umrechnen (3.3V Referenz)
        voltage = round(value / 255.0 * 3.3, 2)
        
        # Prozentwert (0-100%)
        percentage = round(value / 255.0 * 100, 1)
        
        return value, voltage, percentage
    except Exception as e:
        print(f"Fehler beim Lesen: {e}")
        return None, None, None

try:
    # Erstes paar Messungen für Kalibrierung
    print("Kalibriere Sensor... bitte 2 Sekunden warten")
    time.sleep(2)
    
    # Speichere Minimal- und Maximalwerte
    min_value = 255
    max_value = 0
    samples = []
    
    print("\nStarte Messung alle 0.5 Sekunden:")
    print("-" * 60)
    
    while True:
        value, voltage, percentage = read_light()
        
        if value is not None:
            # Aktualisiere Min/Max
            min_value = min(min_value, value)
            max_value = max(max_value, value)
            
            samples.append(value)
            if len(samples) > 10:
                samples.pop(0)
            avg_value = sum(samples) / len(samples)
            
            # Lichtstärke als Balken visualisieren
            bar_length = int(percentage / 5)  # 20 Balken = 100%
            bar = "█" * bar_length + "░" * (20 - bar_length)
            
            # Zeitstempel
            timestamp = time.strftime("%H:%M:%S")
            
            # Lichtstatus bestimmen
            if value < 50:
                status = "🌑 SEHR DUNKEL"
            elif value < 100:
                status = "🌙 DUNKEL"
            elif value < 150:
                status = "⛅ NORMAL"
            elif value < 200:
                status = "☀️ HELL"
            else:
                status = "🔥 SEHR HELL"
            
            # Ausgabe
            print(f"[{timestamp}] {status}")
            print(f"  Wert: {value:3d}/255 | Spannung: {voltage:.2f}V | {percentage:5.1f}%")
            print(f"  [{bar}]")
            print(f"  Min: {min_value:3d} | Max: {max_value:3d} | Avg: {avg_value:3.0f}")
            print()
        
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nTest beendet.")
    print(f"\nStatistik während der Messung:")
    print(f"  Minimalwert: {min_value}")
    print(f"  Maximalwert: {max_value}")
    print(f"  Dynamikumfang: {max_value - min_value}")

except Exception as e:
    print(f"\nFehler: {e}")

finally:
    GPIO.cleanup()
    print("GPIO aufgeräumt")