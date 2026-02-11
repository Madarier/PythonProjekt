#!/usr/bin/env python3
from pitop.pma import LightSensor
from time import sleep
from datetime import datetime

# Lichtsensor an A0 initialisieren
light_sensor = LightSensor("A0")

print("=" * 60)
print("🌞 PI-TOP LICHTSENSOR TEST (A0)")
print("=" * 60)
print("Sensor an A0 angeschlossen")
print("\n📊 Zeige Lichtwerte in Echtzeit")
print("   Strg+C zum Beenden")
print("-" * 60)

# Für Statistik
min_value = 100
max_value = 0
samples = []

try:
    while True:
        # Sensorwert lesen (0-100)
        value = light_sensor.reading
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Statistik aktualisieren
        min_value = min(min_value, value)
        max_value = max(max_value, value)
        
        samples.append(value)
        if len(samples) > 20:
            samples.pop(0)
        avg_value = sum(samples) / len(samples)
        
        # Lichtstatus bestimmen
        if value < 10:
            status = "🌑 SEHR DUNKEL"
            icon = "⬛"
        elif value < 25:
            status = "🌙 DUNKEL"
            icon = "🌙"
        elif value < 50:
            status = "⛅ NORMAL"
            icon = "⛅"
        elif value < 75:
            status = "☀️ HELL"
            icon = "☀️"
        else:
            status = "🔥 SEHR HELL"
            icon = "🔥"
        
        # Balkendiagramm
        bar_length = int(value / 5)  # 20 Balken = 100%
        bar = "█" * bar_length + "░" * (20 - bar_length)
        
        # Ausgabe
        print(f"[{timestamp}] {icon} {status}")
        print(f"   Wert: {value:3.0f}%  [{bar}]")
        print(f"   Min: {min_value:3.0f}% | Max: {max_value:3.0f}% | Ø: {avg_value:3.0f}%")
        print()
        
        sleep(0.3)

except KeyboardInterrupt:
    print("\n" + "=" * 60)
    print("📊 TEST BEENDET - STATISTIK")
    print("=" * 60)
    print(f"   Minimalwert:  {min_value:.0f}%")
    print(f"   Maximalwert:  {max_value:.0f}%")
    print(f"   Durchschnitt: {sum(samples)/len(samples):.0f}%")
    print(f"   Messungen:    {len(samples)}")
    print("=" * 60)