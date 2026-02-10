#!/usr/bin/env python3
from gpiozero import Button
import time

print("🧪 KOMPLETTER BUTTON TEST")
print("=" * 50)

# Liste von möglichen GPIO Pins zum Testen
test_pins = [27, 17, 4, 22, 23, 24, 25, 5, 6, 13, 19, 26]

def test_pin(pin_number):
    """Testet einen spezifischen GPIO Pin"""
    print(f"\n🔍 Teste BCM {pin_number}...")
    
    try:
        # Button mit internem Pull-Up
        button = Button(pin_number, pull_up=True)
        print(f"  ✅ Pin {pin_number} initialisiert")
        
        # Kurz testen
        for i in range(3):
            time.sleep(0.5)
            if button.is_pressed:
                print(f"  🎯 PIN {pin_number} WIRD GEDRÜCKT!")
                return True
        
        print(f"  ⏳ Pin {pin_number} - Kein Druck erkannt")
        button.close()
        return False
        
    except Exception as e:
        print(f"  ❌ Pin {pin_number} Fehler: {e}")
        return False

# Haupttest
print("Verbinde nun den Button zwischen einem GPIO Pin und GND.")
print("Das Script testet automatisch alle möglichen Pins.\n")

for pin in test_pins:
    test_pin(pin)

print("\n" + "=" * 50)
print("💡 HINWEISE:")
print("- Button muss zwischen GPIO und GND angeschlossen sein")
print("- Drücke den Button während das Script läuft")
print("- GND Pins: 6, 9, 14, 20, 25, 30, 34, 39")
print("\nZum direkten Test: python3 -c \"from gpiozero import Button; b = Button(27); print('Pressed' if b.is_pressed else 'Not pressed')\"")