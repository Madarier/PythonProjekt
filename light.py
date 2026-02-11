#!/usr/bin/env python3
from pitop import Pitop
from pitop.common.i2c import I2CDevice
import time

# Pi-Top initialisieren
pitop = Pitop()

# I2C ADC initialisieren (Pi-Top hat einen internen ADC)
I2C_BUS = 1
ADC_ADDRESS = 0x48  # Standard für Pi-Top ADC

def read_light_sensor():
    """Liest den LDR-Lichtsensor an Port A0 (EZ-Connect)"""
    try:
        # I2C-Verbindung öffnen
        i2c = I2CDevice(I2C_BUS, ADC_ADDRESS)
        
        # A0 = Kanal 0
        # Kommando für Single-Ended, Kanal 0
        cmd = 0x84
        i2c.write(cmd.to_bytes(1, 'big'))
        
        # Wert lesen (8-bit, 0-255)
        data = i2c.read(1)
        value = int.from_bytes(data, 'big')
        
        # In Prozent umrechnen (0-100%)
        percent = (value / 255) * 100
        
        return value, percent
        
    except Exception as e:
        print(f"Fehler beim Lesen: {e}")
        return None, None

print("=" * 50)
print("PI-TOP LDR LICHTSENSOR TEST")
print("=" * 50)
print("Sensor an A0 (EZ-Connect) angeschlossen")
print("Drücke Strg+C zum Beenden")
print("-" * 50)

try:
    while True:
        value, percent = read_light_sensor()
        
        if value is not None:
            # Einfache Status-Anzeige
            if percent < 20:
                status = "🌑 SEHR DUNKEL"
            elif percent < 40:
                status = "🌙 DUNKEL"
            elif percent < 60:
                status = "⛅ NORMAL"
            elif percent < 80:
                status = "☀️ HELL"
            else:
                status = "🔥 SEHR HELL"
            
            # Klare, einfache Ausgabe
            print(f"[{time.strftime('%H:%M:%S')}] {status}")
            print(f"  Wert: {value:3d}/255 | {percent:5.1f}%")
            print()
        
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nTest beendet.")