import time
import sys
import RPi.GPIO as GPIO

BUTTON_PIN = 26

# Use BCM GPIO numbering
GPIO.setmode(GPIO.BCM)

# Configure the pin as input with internal Pull-Up resistor
# (Released = HIGH / 1, Pressed = LOW / 0)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print(f"GPIO {BUTTON_PIN} Debugging Tool Started.")
print("Monitoring pin state. Press Ctrl+C to exit.\n")

last_state = GPIO.input(BUTTON_PIN)
print(f"Initial State: {'HIGH (1) [Released]' if last_state else 'LOW (0) [Pressed]'}")

try:
    while True:
        state = GPIO.input(BUTTON_PIN)
        if state != last_state:
            if state == GPIO.LOW:
                print("Button Pressed (LOW / 0)")
            else:
                print("Button Released (HIGH / 1)")
            last_state = state
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nCleaning up GPIO and exiting...")
finally:
    GPIO.cleanup()
