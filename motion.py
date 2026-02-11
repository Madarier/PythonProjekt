#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Ändere diesen Wert je nachdem welcher Pin funktioniert
PIR_PIN = 7  # Probiere: 8, dann 7

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

print(f"PIR Test auf GPIO{PIR_PIN}")
print("Kalibriere... (5 Sekunden)")
time.sleep(5)
print("Bereit! Bewege dich vor dem Sensor...")

while True:
    if GPIO.input(PIR_PIN):
        print(f"BEWEGUNG! {time.strftime('%H:%M:%S')}")
        time.sleep(1)
    time.sleep(0.1)