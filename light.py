#!/usr/bin/env python3
import time
from pitop import Pitop
from pitop.common.i2c import I2CDevice
import smbus

print("=" * 60)
print("PI-TOP LICHTSENSOR TEST (A0)")
print("=" * 60)
print("Sensor an A0 (P1/P0) angeschlossen")
print("\nDrücke Strg+C zum Beenden")
print("-" * 60)

# I2C Konfiguration für Pi-Top ADC
I2C_BUS = 1
ADC_ADDRESS = 0x48  # Typische Pi-Top ADC Adresse

def read_ads7830(channel=0):
    """Liest Kanal 0-7 vom ADS7830 ADC"""
    try:
        bus = smbus.SMBus(I2C_BUS)
        
        # ADS7830 Kommando: 
        # Bit 7: 1 = Start
        # Bit 6-4: 100 = Single-Ended Mode
        # Bit 3-2: SD, SEL1, SEL0 für Kanalwahl
        # Bit 1-0: 00 (reserviert)
        
        if channel == 0:
            cmd = 0x84  # Kanal 0
        elif channel == 1:
            cmd = 0xC4  # Kanal 1
        elif channel == 2:
            cmd = 0x94  # Kanal 2
        elif channel == 3:
            cmd = 0xD4  # Kanal 3
        elif channel == 4:
            cmd = 0xA4  # Kanal 4
        elif channel == 5:
            cmd = 0xE4  # Kanal 5
        elif channel == 6:
            cmd = 0xB4  # Kanal 6
        elif channel == 7:
            cmd = 0xF4  # Kanal 7
        else:
            return 0
            
        bus.write_byte(ADC_ADDRESS, cmd)
        value = bus.read_byte(ADC_ADDRESS)
        bus.close()
        return value
        
    except Exception as e:
        print(f"I2C Fehler: {e}")
        return None

def read_light():
    """Liest Lichtwert von A0"""
    # A0 = Kanal 0
    raw_value = read_ads7830(0)
    
    if raw_value is not None:
        # In Prozent umrechnen (0-255 -> 0-100%)
        percentage = (raw_value / 255) * 100
        
        # Spannung berechnen (3.3V Referenz)
        voltage = (raw_value / 255) * 3.3
        
        return raw_value, percentage, voltage
    else:
        return None, None, None

try:
    # Teste I2C Verbindung
    print("Prüfe I2C Verbindung...")
    bus = smbus.SMBus(1)
    bus.read_byte(ADC_ADDRESS)
    bus.close()
    print(f"✓ ADC gefunden an Adresse 0x{ADC_ADDRESS:02X}")
    print()
    
    # Kalibrierung
    print("Kalibriere Sensor... 2 Sekunden")
    time.sleep(2)
    
    min_val = 255
    max_val = 0
    samples = []
    
    print("Starte Messung (alle 0.5s):")
    print("-" * 60)
    
    while True:
        raw, percent, voltage = read_light()
        
        if raw is not None:
            # Min/Max aktualisieren
            min_val = min(min_val, raw)
            max_val = max(max_val, raw)
            
            samples.append(percent)
            if len(samples) > 10:
                samples.pop(0)
            avg_percent = sum(samples) / len(samples)
            
            # Status bestimmen
            if percent < 10:
                status = "🌑 SEHR DUNKEL"
            elif percent < 25:
                status = "🌙 DUNKEL"
            elif percent < 50:
                status = "⛅ NORMAL"
            elif percent < 75:
                status = "☀️ HELL"
            else:
                status = "🔥 SEHR HELL"
            
            # Balkenanzeige
            bars = int(percent / 5)
            bar = "█" * bars + "░" * (20 - bars)
            
            # Ausgabe
            print(f"[{time.strftime('%H:%M:%S')}] {status}")
            print(f"  Rohwert: {raw:3d}/255 | {percent:5.1f}% | {voltage:.2f}V")
            print(f"  [{bar}]")
            print(f"  Min: {min_val:3d} | Max: {max_val:3d} | Ø: {avg_percent:3.0f}%")
            print()
        
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nTest beendet!")
    print(f"\nStatistik:")
    print(f"  Minimal: {min_val}")
    print(f"  Maximal: {max_val}")
    print(f"  Bereich: {max_val - min_val}")

except Exception as e:
    print(f"\nFehler: {e}")
    print("\nMögliche Lösungen:")
    print("1. Prüfe ob der Sensor richtig an A0 angeschlossen ist")
    print("2. Führe aus: sudo i2cdetect -y 1")
    print("3. Installiere: sudo apt install python3-smbus")