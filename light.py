#!/usr/bin/env python3
import time
import RPi.GPIO as GPIO
import spidev  # Für SPI-ADC (MCP3008)

# GPIO Modus setzen
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

print("=" * 60)
print("PI-TOP LICHTSENSOR TEST (A0 - P1/P0)")
print("=" * 60)
print("Sensor an A0 (P1/P0) angeschlossen")
print("\nDrücke Strg+C zum Beenden")
print("-" * 60)

# SPI für MCP3008 ADC initialisieren (Pi-Top verwendet oft MCP3008)
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # Bus 0, Device 0 (CE0)
    spi.max_speed_hz = 1000000
    print("✓ SPI initialisiert (MCP3008)")
    adc_type = "MCP3008"
except:
    print("⚠️ Kein MCP3008 gefunden, versuche ADS7830...")
    adc_type = "ADS7830"

def read_mcp3008(channel):
    """Liest Kanal 0-7 vom MCP3008 ADC"""
    if channel < 0 or channel > 7:
        return 0
    
    # MCP3008 Kommando: Startbit, Single-Ended Mode, Kanal
    cmd = [1, (8 + channel) << 4, 0]
    response = spi.xfer2(cmd)
    
    # 10-bit Wert extrahieren (0-1023)
    value = ((response[1] & 3) << 8) + response[2]
    return value

def read_ads7830(channel):
    """Liest Kanal 0-7 vom ADS7830 ADC (I2C)"""
    import smbus
    try:
        bus = smbus.SMBus(1)
        # ADS7830 Kommando für Single-Ended Mode
        cmd = 0x84 | (channel << 4)
        bus.write_byte(0x48, cmd)  # Standard-Adresse 0x48
        value = bus.read_byte(0x48)
        bus.close()
        return value * 4  # 8-bit zu 10-bit Skalierung
    except:
        return None

def read_light():
    """Liest Lichtwert von A0"""
    if adc_type == "MCP3008":
        value = read_mcp3008(0)  # Kanal 0 = A0
        if value:
            percent = (value / 1023) * 100
            voltage = (value / 1023) * 3.3
            return value, percent, voltage
    else:
        value = read_ads7830(0)  # Kanal 0 = A0
        if value:
            percent = (value / 1023) * 100
            voltage = (value / 1023) * 3.3
            return value, percent, voltage
    
    return None, None, None

try:
    # Teste Verbindung
    print("Teste ADC Verbindung...")
    test_value, _, _ = read_light()
    
    if test_value is not None:
        print(f"✓ ADC gefunden, erster Wert: {test_value}")
        print()
    else:
        print("❌ Kein ADC gefunden!")
        print("Prüfe Verkabelung und SPI/I2C")
        exit(1)
    
    # Kalibrierung
    print("Kalibriere Sensor... 2 Sekunden")
    time.sleep(2)
    
    min_val = 9999
    max_val = 0
    samples = []
    
    print("\nStarte Messung (alle 0.5s):")
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
            print(f"  Rohwert: {raw:4d}/1023 | {percent:5.1f}% | {voltage:.2f}V")
            print(f"  [{bar}]")
            print(f"  Min: {min_val:4d} | Max: {max_val:4d} | Ø: {avg_percent:3.0f}%")
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

finally:
    if 'spi' in locals():
        spi.close()
    GPIO.cleanup()