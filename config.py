import os

# Server Configurations
PORT = 5000
HOST = "0.0.0.0"

# Directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
SCREENSHOTS_DIR = os.path.join(STATIC_DIR, "screenshots")

# Create folders if they don't exist
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Audio Parameters (INMP441 I2S Microphone)
AUDIO_SAMPLE_RATE = 16000     # 16kHz standard for voice and scream analysis
AUDIO_CHUNK_SIZE = 1024       # Buffer block size
AUDIO_CHANNELS = 1            # Mono recording
AUDIO_DEVICE_NAME = "i2s"      # Search for audio devices matching this, or fallback to default

# Scream Detection Parameters
AUDIO_SCREAM_FREQ_MIN = 1000   # Hz (Bottom end of screaming range)
AUDIO_SCREAM_FREQ_MAX = 3500   # Hz (Top end of screaming frequency peak)
AUDIO_SCREAM_THRESHOLD = 0.15  # Energy threshold (normalized relative to frequency bins)
AUDIO_SCREAM_DURATION = 0.3    # Screaming duration required to trigger (seconds)

# Sensor Parameters (ADS1115 & Pulse Heart Rate)
ADS_CHANNEL = 0               # Channel A0
HEART_RATE_SAMPLE_RATE = 50   # Hz (Readings per second, 20ms intervals)
PPG_BUFFER_SIZE = 150         # Store 3 seconds of rolling data at 50Hz
BPM_MIN = 45                  # Minimum valid BPM
BPM_MAX = 185                 # Maximum valid BPM

# OLED Parameters (SSD1306)
OLED_I2C_ADDR = 0x3C          # Standard I2C address for SSD1306
OLED_WIDTH = 128
OLED_HEIGHT = 64

# Camera Parameters
CAM_WIDTH = 640
CAM_HEIGHT = 480
CAM_FPS = 15                  # Keep low to save Pi Zero CPU

# Push Button Parameters
BUTTON_GPIO_PIN = 26          # GPIO 26 (Physical Pin 37)
BUTTON_HOLD_TIME = 3.0        # Duration in seconds to hold the button to toggle mode

