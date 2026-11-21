import time
import math
import os
import sys
import threading
import collections
from datetime import datetime
import numpy as np
import cv2

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None

# Import configurations
import config

# Try importing hardware libraries, fail gracefully with printed warnings if they aren't fully configured
try:
    import pyaudio
except ImportError:
    print("WARNING: pyaudio not found. Please install python3-pyaudio.")
    pyaudio = None

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
except ImportError:
    print("WARNING: Adafruit CircuitPython ADS1x15 libraries not found.")
    board, busio, ADS, AnalogIn = None, None, None, None

try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("WARNING: luma.oled and PIL libraries not found.")
    ssd1306, canvas, Image, ImageDraw, ImageFont = None, None, None, None, None

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("WARNING: RPi.GPIO not found. Button monitoring will be simulated.")
    GPIO = None


class GlobalState:
    """Manages the synchronized state of the safety system."""
    def __init__(self):
        self.state = "resting"  # "resting" or "triggered"
        self.heart_rate = 0     # Real-time calculated BPM
        self.mic_frequency = 0.0 # Peak frequency in Hz
        self.mic_amplitude = 0.0 # Noise volume level (RMS)
        self.triggered_time = None
        self.last_trigger_source = None # "audio" or "remote"
        self.captured_faces_count = 0
        self.latest_frame = None  # Holds the latest JPEG byte stream for the MJPEG stream
        self.screenshots_cache = {} # In-memory cache for captured screenshots: {filename: jpeg_bytes}
        self.lock = threading.Lock()
        self.audio_queue = collections.deque(maxlen=100) # Holds raw PCM chunks for streaming

    def trigger(self, source="audio"):
        with self.lock:
            if self.state == "resting":
                self.state = "triggered"
                self.triggered_time = datetime.now()
                self.last_trigger_source = source
                print(f"[{datetime.now()}] >>> SYSTEM TRIGGERED via {source}! <<<")
                return True
            return False

    def reset(self):
        with self.lock:
            if self.state == "triggered":
                self.state = "resting"
                self.triggered_time = None
                self.last_trigger_source = None
                self.latest_frame = None
                print(f"[{datetime.now()}] >>> SYSTEM RESET to resting state <<<")
                return True
            return False

    def get_status_dict(self):
        with self.lock:
            duration = 0
            if self.triggered_time:
                duration = int((datetime.now() - self.triggered_time).total_seconds())
            return {
                "state": self.state,
                "heart_rate": self.heart_rate,
                "mic_frequency": round(self.mic_frequency, 1),
                "mic_amplitude": round(self.mic_amplitude, 4),
                "triggered_time": self.triggered_time.isoformat() if self.triggered_time else None,
                "duration_seconds": duration,
                "last_trigger_source": self.last_trigger_source,
                "captured_faces_count": self.captured_faces_count
            }


# Share the global state between threads
system_state = GlobalState()


class AudioMonitor(threading.Thread):
    """
    Captures audio from the INMP441 I2S microphone, calculates spectral energy via FFT,
    detects high-pitched screaming frequencies, and maintains an audio stream buffer.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def find_i2s_device(self, pa):
        """Scans for the I2S microphone or defaults to standard capture."""
        device_index = None
        try:
            info = pa.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            for i in range(0, numdevices):
                dev_info = pa.get_device_info_by_host_api_device_index(0, i)
                name = dev_info.get('name', '').lower()
                if dev_info.get('maxInputChannels') > 0:
                    print(f"Audio Input Device [{i}]: {dev_info.get('name')}")
                    if config.AUDIO_DEVICE_NAME in name or "snd_rpi_i2s" in name or "dmic" in name:
                        device_index = i
                        print(f"-> Selected targeted I2S device: {dev_info.get('name')} at index {i}")
                        break
        except Exception as e:
            print(f"Error listing audio devices: {e}")
        return device_index

    def run(self):
        if pyaudio is None:
            print("Audio Monitor NOT running: PyAudio is not installed.")
            return

        pa = pyaudio.PyAudio()
        device_index = self.find_i2s_device(pa)

        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=config.AUDIO_CHANNELS,
                rate=config.AUDIO_SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=config.AUDIO_CHUNK_SIZE
            )
            print("Audio Stream opened successfully.")
        except Exception as e:
            print(f"FATAL: Failed to open audio stream: {e}")
            pa.terminate()
            return

        scream_frames_count = 0
        scream_frames_required = 23 # 1.5 seconds (23 chunks * 64ms = 1.47s)

        while self.running:
            try:
                # Read audio block (non-blocking read/exception ignored to prevent Pi dropouts)
                data_bytes = stream.read(config.AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                
                # Buffer raw PCM data chunks for the Flask /audio_feed endpoint only when triggered
                if system_state.state == "triggered":
                    system_state.audio_queue.append(data_bytes)
                else:
                    system_state.audio_queue.clear()

                # Convert binary data to floating point values for analysis
                data_numeric = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                if len(data_numeric) == 0:
                    continue

                # Calculate volume (Root-Mean-Square)
                rms = np.sqrt(np.mean(data_numeric**2))
                system_state.mic_amplitude = float(rms)

                # Perform FFT
                fft_coeffs = np.fft.rfft(data_numeric)
                freqs = np.fft.rfftfreq(len(data_numeric), 1.0 / config.AUDIO_SAMPLE_RATE)
                magnitudes = np.abs(fft_coeffs)

                if len(magnitudes) == 0:
                    continue

                # Find peak frequency
                peak_idx = np.argmax(magnitudes)
                peak_freq = freqs[peak_idx]
                
                # Apply parabolic interpolation for extreme high-precision pitch detection
                # This overcomes the discrete bin limitation (15.6Hz step size) of the FFT
                if 0 < peak_idx < len(magnitudes) - 1:
                    alpha = magnitudes[peak_idx - 1]
                    beta = magnitudes[peak_idx]
                    gamma = magnitudes[peak_idx + 1]
                    denom = alpha - 2 * beta + gamma
                    if abs(denom) > 1e-5:
                        p = 0.5 * (alpha - gamma) / denom
                        peak_freq = (peak_idx + p) * (config.AUDIO_SAMPLE_RATE / config.AUDIO_CHUNK_SIZE)
                
                system_state.mic_frequency = float(peak_freq)

                # Scream detection logic:
                # Triggers if the integer frequency shown on the OLED is between 955-1005Hz
                display_freq = int(round(peak_freq))
                if 955 <= display_freq <= 1005:
                    if rms > 0.01:
                        scream_frames_count += 1
                        # Print debug info to console to see the progress
                        if scream_frames_count % 5 == 0 or scream_frames_count == 1:
                            print(f"[DEBUG MIC] Freq Match: freq={display_freq}Hz, rms={rms:.5f} (>0.01), frames={scream_frames_count}/30")
                        if scream_frames_count >= 30: # ~2.0 second trigger
                            # 955-1005Hz sustained tone detected! Trigger the alarm
                            triggered = system_state.trigger(source="audio")
                            if triggered:
                                print(f"*** 955-1005Hz TARGET SIGNAL DETECTED! peak_freq={display_freq}Hz sustained ***")
                    else:
                        scream_frames_count = max(0, scream_frames_count - 1)
                        if time.time() % 1.0 < 0.1: # Limit print rate of quiet matches to avoid terminal spam
                            print(f"[DEBUG MIC] Freq Match but too QUIET: freq={display_freq}Hz, rms={rms:.5f} (threshold is >0.01)")
                else:
                    # Decay slowly by 1 on signal dropout to prevent resetting on minor jitters
                    scream_frames_count = max(0, scream_frames_count - 1)

            except Exception as e:
                print(f"Error in Audio Monitor thread: {e}")
                time.sleep(0.1)

        # Cleanup
        try:
            stream.stop_stream()
            stream.close()
        except:
            pass
        pa.terminate()


class SensorMonitor(threading.Thread):
    """
    Polls the ADS1115 I2C ADC to read the heart rate sensor (A0).
    Processes the raw pulse wave using peak-detection to compute BPM.
    Simultaneously drives the I2C SSD1306 OLED display to draw the Watch UI.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        
        # ADS1115 setup
        self.ads = None
        self.adc_chan = None
        if board is not None and ADS is not None:
            try:
                i2c_bus = busio.I2C(board.SCL, board.SDA)
                self.ads = ADS.ADS1115(i2c_bus, address=0x48)
                self.adc_chan = AnalogIn(self.ads, 0)
                print("ADS1115 initialized successfully.")
            except Exception as e:
                print(f"Error initializing ADS1115: {e}")

        # OLED SSD1306 setup
        self.oled = None
        if ssd1306 is not None:
            try:
                # OLED is on same I2C bus
                serial = i2c(port=config.I2C_BUS_ID if hasattr(config, 'I2C_BUS_ID') else 1, address=config.OLED_I2C_ADDR)
                self.oled = ssd1306(serial)
                print("SSD1306 OLED initialized successfully.")
            except Exception as e:
                print(f"Error initializing OLED: {e}")

    def run(self):
        # Rolling buffer for PPG values
        ppg_buffer = collections.deque(maxlen=config.PPG_BUFFER_SIZE)
        
        # Timestamps of heart rate peaks
        peak_times = collections.deque(maxlen=5)
        
        # Filtering parameters
        last_smoothed = 0
        peak_cooldown = 0.35  # seconds (equivalent to 170 BPM max)
        last_peak_time = 0

        # OLED font setup
        font_large = None
        font_small = None
        if ImageFont is not None:
            # Try to load default Raspbian system fonts, fallback to default PIL font
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
            ]
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font_large = ImageFont.truetype(path, 18)
                        font_small = ImageFont.truetype(path, 9)
                        print(f"Loaded OLED font: {path}")
                        break
                    except:
                        pass
            if font_large is None:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # Dynamic loop pacing
        poll_interval = 1.0 / config.HEART_RATE_SAMPLE_RATE # 20ms at 50Hz
        oled_update_ticks = 0
        oled_ticks_divider = 5  # Update OLED at 10Hz (50Hz / 5)
        
        flash_toggle = False
        flash_ticks = 0

        while self.running:
            start_time = time.time()

            # 1. READ ADS1115 HEART RATE VALUES
            raw_val = 0
            if self.adc_chan is not None:
                try:
                    raw_val = self.adc_chan.value
                except Exception as e:
                    print(f"Error reading ADS1115 A0: {e}")
            else:
                # Simulate normal resting heartbeat signal if ADC is missing
                # A combination of breathing baseline (low freq) + pulse peaks (1.2Hz) + noise
                t = time.time()
                pulse = 0.3 * math.sin(2 * math.pi * 1.25 * t)  # 75 BPM base
                dicrotic = 0.1 * math.sin(2 * math.pi * 2.5 * t - 0.5)
                noise = 0.02 * math.sin(2 * math.pi * 30 * t)
                raw_val = int((pulse + dicrotic + noise + 1.0) * 15000)

            # 2. RUN HEART RATE PROCESSING (PPG FILTERING & PEAK EXTRACTION)
            # Check for physical finger presence / sensor saturation
            # 16-bit ADC raw_val ranges from 0 to ~32767 (or 65535 if unsigned)
            finger_on_sensor = True
            if raw_val > 62000 or raw_val < 3000:
                finger_on_sensor = False

            # Heavier low-pass smoothing filter (eliminates dicrotic notch/50Hz hum)
            smoothed = 0.90 * last_smoothed + 0.10 * raw_val
            last_smoothed = smoothed

            ppg_buffer.append(smoothed)

            if len(ppg_buffer) >= 20:
                # DC Subtraction: Subtract the slow moving average (baseline drift)
                mean_baseline = np.mean(ppg_buffer)
                signal = smoothed - mean_baseline

                # Calculate AC signal amplitude to detect finger presence
                sig_min = np.min(ppg_buffer)
                sig_max = np.max(ppg_buffer)
                ac_amplitude = sig_max - sig_min

                # If signal is too flat, no finger is placed
                if ac_amplitude < 400:
                    finger_on_sensor = False

                if finger_on_sensor:
                    # Peak detection with adaptive thresholding
                    threshold = max(350, 0.40 * (sig_max - mean_baseline))

                    now = time.time()
                    # Check for local peak (zero-crossing of derivative from positive to negative)
                    if len(ppg_buffer) >= 3:
                        y2 = ppg_buffer[-1] - mean_baseline
                        y1 = ppg_buffer[-2] - mean_baseline
                        y0 = ppg_buffer[-3] - mean_baseline

                        if y1 > threshold and y1 > y0 and y2 < y1:
                            # Strict peak cooldown (330ms refractory period prevents double-triggering)
                            if now - last_peak_time > 0.33:
                                peak_interval = now - last_peak_time
                                last_peak_time = now

                                bpm = 60.0 / peak_interval
                                if config.BPM_MIN <= bpm <= config.BPM_MAX:
                                    if len(peak_times) == 0:
                                        # Seed the list
                                        peak_times.extend([bpm] * 5)
                                    else:
                                        peak_times.append(bpm)
                                    
                                    # Stable, outlier-immune Rolling Median of last 7 beats
                                    system_state.heart_rate = int(np.median(peak_times))
                else:
                    # Finger removed - reset telemetry
                    system_state.heart_rate = 0
                    peak_times.clear()
            
            # If finger is off or no heartbeat for 3.5s, drop reading
            if time.time() - last_peak_time > 3.5:
                system_state.heart_rate = 0
                peak_times.clear()

            # 3. DRAW OLED WATCH DISPLAY (AT 10Hz)
            if self.oled is not None and oled_update_ticks % oled_ticks_divider == 0:
                # Heart animation scale
                heart_pulse = int(5 + 3 * math.sin(2 * math.pi * (system_state.heart_rate/60.0) * time.time()))
                if system_state.heart_rate == 0:
                    heart_pulse = 5

                # Toggle screen flashing in triggered state every 0.3s
                if system_state.state == "triggered":
                    flash_ticks += 1
                    if flash_ticks >= 3:
                        flash_toggle = not flash_toggle
                        flash_ticks = 0
                        try:
                            self.oled.invert(flash_toggle)
                        except:
                            pass
                else:
                    if flash_toggle:
                        flash_toggle = False
                        try:
                            self.oled.invert(False)
                        except:
                            pass

                # Draw UI using luma.oled canvas
                try:
                    with canvas(self.oled) as draw:
                        # Clear screen
                        draw.rectangle((0, 0, config.OLED_WIDTH - 1, config.OLED_HEIGHT - 1), fill=0, outline=0)

                        # Top Area: Telemetry
                        # Draw tiny heart shape
                        hx, hy = 8, 8
                        draw.polygon([(hx, hy-3), (hx-3, hy-6), (hx-6, hy-3), (hx, hy+3), (hx+6, hy-3), (hx+3, hy-6)], fill=1)
                        
                        bpm_str = f"{system_state.heart_rate}" if system_state.heart_rate > 0 else "--"
                        draw.text((18, 2), f"{bpm_str} BPM", fill=1, font=font_small)

                        # Mic noise indicator on right
                        mic_freq = int(system_state.mic_frequency)
                        draw.text((80, 2), f"♫ {mic_freq}Hz", fill=1, font=font_small)

                        # Center Watch Face: Large Clock
                        time_str = datetime.now().strftime("%H:%M:%S")
                        date_str = datetime.now().strftime("%a, %b %d")

                        # Center-aligned text placement
                        # Clock string is 8 characters. Width is roughly 8 chars * 12px = 96px
                        draw.text((32, 16), time_str, fill=1, font=font_large)
                        draw.text((38, 36), date_str, fill=1, font=font_small)

                        # Bottom Area: State bar
                        if system_state.state == "triggered":
                            # Glowing/inverted danger bar
                            draw.rectangle((0, 50, config.OLED_WIDTH - 1, config.OLED_HEIGHT - 1), fill=1)
                            draw.text((24, 52), "!! DANGER !!", fill=0, font=font_small)
                        else:
                            # Resting state bar
                            draw.rectangle((0, 50, config.OLED_WIDTH - 1, config.OLED_HEIGHT - 1), fill=0, outline=1)
                            draw.text((34, 52), "[ RESTING ]", fill=1, font=font_small)

                except Exception as ex:
                    print(f"OLED Draw Error: {ex}")

            # Pace the thread loop
            oled_update_ticks += 1
            elapsed = time.time() - start_time
            sleep_time = poll_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


class CameraMonitor(threading.Thread):
    """
    Controls the Pi Camera.
    Spawns in the 'triggered' state, runs fast face detection with OpenCV,
    saves screen captures of all shown faces to local disk,
    and buffers JPEG frames for the Flask MJPEG stream.
    Releases the camera in 'resting' state to conserve CPU.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.use_opencv = True
        self.start_frame_saved = False
        
        # Load high-accuracy alt2 Haar Cascade
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        if self.face_cascade.empty():
            print("WARNING: High-accuracy Haar Cascade XML failed to load. Face detection disabled.")

    def draw_tech_corners(self, img, x, y, w, h, color, size=15, thickness=2):
        """Draws cool high-tech targeted corner brackets around a face."""
        # Top-Left corner
        cv2.line(img, (x, y), (x + size, y), color, thickness)
        cv2.line(img, (x, y), (x, y + size), color, thickness)
        # Top-Right corner
        cv2.line(img, (x + w, y), (x + w - size, y), color, thickness)
        cv2.line(img, (x + w, y), (x + w, y + size), color, thickness)
        # Bottom-Left corner
        cv2.line(img, (x, y + h), (x + size, y + h), color, thickness)
        cv2.line(img, (x, y + h), (x, y + h - size), color, thickness)
        # Bottom-Right corner
        cv2.line(img, (x + w, y + h), (x + w - size, y + h), color, thickness)
        cv2.line(img, (x + w, y + h), (x + w, y + h - size), color, thickness)

    def run(self):
        cap = None
        picam = None
        last_screenshot_time = 0
        screenshot_cooldown = 1.5 # seconds between screenshots
        opencv_fail_count = 0
        frame_ticks = 0
        self.current_faces = []

        while self.running:
            # Active camera loop runs ONLY when triggered
            if system_state.state == "triggered":
                if cap is None and picam is None:
                    if self.use_opencv:
                        # Open Pi Camera / USB Webcam
                        print("Activating Pi Camera module (OpenCV)...")
                        cap = cv2.VideoCapture(0)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_WIDTH)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_HEIGHT)
                        time.sleep(0.5) # Allow camera sensor to warm up
                        if not cap.isOpened():
                            print("OpenCV VideoCapture failed. Falling back to Picamera2 (modern RPi stack)...")
                            cap.release()
                            cap = None
                            self.use_opencv = False
                            continue
                    
                if cap is None and picam is None and not self.use_opencv:
                    if Picamera2 is not None:
                        try:
                            print("Activating Pi Camera module (Picamera2)...")
                            picam = Picamera2()
                            cam_config = picam.create_preview_configuration(main={"size": (config.CAM_WIDTH, config.CAM_HEIGHT)})
                            picam.configure(cam_config)
                            picam.start()
                            print("Picamera2 camera started successfully.")
                        except Exception as cam_err:
                            print(f"ERROR: Picamera2 initialization failed: {cam_err}")
                            picam = None
                            time.sleep(2.0)
                            continue
                    else:
                        print("ERROR: OpenCV is bypassed and Picamera2 library is unavailable.")
                        time.sleep(2.0)
                        continue

                frame = None
                if cap is not None:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        opencv_fail_count += 1
                        print(f"ERROR: Failed to read frame from OpenCV ({opencv_fail_count}/5).")
                        if opencv_fail_count >= 5:
                            print("OpenCV is failing to read active buffers. Releasing OpenCV and falling back to Picamera2...")
                            cap.release()
                            cap = None
                            self.use_opencv = False
                            opencv_fail_count = 0
                        time.sleep(0.1)
                        continue
                    else:
                        # Reset failure count on successful read
                        opencv_fail_count = 0
                elif picam is not None:
                    try:
                        frame_rgb = picam.capture_array()
                        # Convert RGB to BGR for standard OpenCV processing
                        frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    except Exception as e:
                        print(f"ERROR: Failed to capture frame from Picamera2: {e}")
                        time.sleep(0.1)
                        continue

                # Mirror frame for intuitive dashboard display
                frame = cv2.flip(frame, 1)

                # Save static alert start frame on the very first capture of the alert session
                if not self.start_frame_saved:
                    self.start_frame_saved = True
                    try:
                        ret_start, start_jpeg = cv2.imencode('.jpg', frame)
                        if ret_start:
                            with system_state.lock:
                                system_state.screenshots_cache["alert_start.jpg"] = start_jpeg.tobytes()
                            print("Static alert start frame cached in memory: alert_start.jpg")
                    except Exception as e:
                        print(f"ERROR: Failed to cache static alert start frame: {e}")

                # Clone frame for screenshot clean saving (no drawings)
                screenshot_frame = frame.copy()

                # Run heavy Haar face detection only once every 4 frames (5Hz on Pi Zero)
                # This decouples the frame rate, keeping the dashboard stream at a buttery smooth 20+ FPS!
                frame_ticks += 1
                if frame_ticks % 4 == 0:
                    scale_factor = 0.5
                    small_frame = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor)
                    gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                    
                    faces = []
                    if not self.face_cascade.empty():
                        faces = self.face_cascade.detectMultiScale(
                            gray,
                            scaleFactor=1.1,
                            minNeighbors=4,
                            minSize=(25, 25)
                        )
                    self.current_faces = faces
                else:
                    # Maintain target tracking display from last detection
                    faces = self.current_faces

                now = time.time()
                face_detected_this_frame = len(faces) > 0

                # Render target indicators around faces
                for (sx, sy, sw, sh) in faces:
                    x = int(sx / 0.5)
                    y = int(sy / 0.5)
                    w = int(sw / 0.5)
                    h = int(sh / 0.5)

                    # Draw high-tech target neon cyan boxes
                    self.draw_tech_corners(frame, x, y, w, h, (255, 240, 0), size=20, thickness=2)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 240, 0), 1)

                    # Neon glowing "TARGET LOCKED" label
                    cv2.putText(
                        frame,
                        "FACE DETECTED",
                        (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 0, 255),
                        1,
                        cv2.LINE_AA
                    )

                # Save snapshot if face detected and cooldown passed
                if face_detected_this_frame and (now - last_screenshot_time > screenshot_cooldown):
                    last_screenshot_time = now
                    
                    # Capture unique file name
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    system_state.captured_faces_count += 1
                    filename = f"face_{timestamp}_{system_state.captured_faces_count}.jpg"

                    # Highlight the primary face in the screenshot with a glowing green border
                    for (sx, sy, sw, sh) in faces:
                        x = int(sx / 0.5)
                        y = int(sy / 0.5)
                        w = int(sw / 0.5)
                        h = int(sh / 0.5)
                        cv2.rectangle(screenshot_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        break

                    try:
                        ret_face, face_jpeg = cv2.imencode('.jpg', screenshot_frame)
                        if ret_face:
                            with system_state.lock:
                                system_state.screenshots_cache[filename] = face_jpeg.tobytes()
                                # Clean up old screenshots to avoid memory leaks (max 50)
                                if len(system_state.screenshots_cache) > 50:
                                    oldest_key = next(iter(system_state.screenshots_cache))
                                    if oldest_key != "alert_start.jpg":
                                        system_state.screenshots_cache.pop(oldest_key, None)
                            print(f"Captured face screenshot cached in memory: {filename}")
                    except Exception as e:
                        print(f"ERROR: Failed to cache face screenshot: {e}")

                # Encode frame as JPEG to stream online
                ret, jpeg = cv2.imencode('.jpg', frame)
                if ret:
                    system_state.latest_frame = jpeg.tobytes()

                # Control FPS rate to limit Pi Zero CPU load (keep sleep small to preserve smoothness)
                time.sleep(0.01)

            else:
                # System is resting - release camera and sleep to save CPU
                if cap is not None:
                    print("Releasing Pi Camera module (resting state)...")
                    cap.release()
                    cap = None
                if picam is not None:
                    print("Releasing Picamera2 module (resting state)...")
                    try:
                        picam.stop()
                        picam.close()
                    except:
                        pass
                    picam = None
                self.use_opencv = True # Reset to retry next time
                self.start_frame_saved = False # Reset start frame trigger
                self.current_faces = []
                frame_ticks = 0
                time.sleep(0.5)

        # Cleanup at program termination
        if cap is not None:
            cap.release()
        if picam is not None:
            try:
                picam.stop()
                picam.close()
            except:
                pass


class ButtonMonitor(threading.Thread):
    """
    Monitors a physical push button on GPIO.
    If held down for 3 seconds, it triggers or resets the safety system.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.pin = config.BUTTON_GPIO_PIN
        self.hold_time = config.BUTTON_HOLD_TIME

        self.gpio_available = False
        if GPIO is not None:
            try:
                # Use BCM numbering
                GPIO.setmode(GPIO.BCM)
                # Configure button pin with pull-up.
                # Since one side is connected to GND, the pin reads LOW when pressed.
                GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self.gpio_available = True
                print(f"Button initialized successfully on GPIO {self.pin} (BCM).")
            except Exception as e:
                print(f"Error initializing GPIO {self.pin} for button: {e}")

    def run(self):
        press_start_time = None
        action_triggered = False

        while self.running:
            if self.gpio_available:
                try:
                    # Read pin state (LOW = pressed, HIGH = released)
                    button_state = GPIO.input(self.pin)
                    is_pressed = (button_state == GPIO.LOW)
                except Exception as e:
                    print(f"Error reading button state: {e}")
                    time.sleep(1.0)
                    continue
            else:
                # Fallback for development/simulation (do nothing)
                time.sleep(1.0)
                continue

            if is_pressed:
                if press_start_time is None:
                    press_start_time = time.time()
                    action_triggered = False
                    print(f"Button press detected on GPIO {self.pin}.")
                else:
                    elapsed = time.time() - press_start_time
                    if elapsed >= self.hold_time and not action_triggered:
                        action_triggered = True
                        if system_state.state == "resting":
                            print(f"Button held for {self.hold_time}s. Triggering system...")
                            system_state.trigger(source="button")
                        else:
                            print(f"Button held for {self.hold_time}s. Resetting system...")
                            system_state.reset()
            else:
                if press_start_time is not None:
                    print(f"Button released after {time.time() - press_start_time:.2f} seconds.")
                    press_start_time = None
                    action_triggered = False

            # Poll every 50ms to keep response quick but CPU load negligible
            time.sleep(0.05)

