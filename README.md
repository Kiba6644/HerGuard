# HerGuard Central - Multi-Modal Hardware Distress Telemetry & Dispatch System

HerGuard Central is a hardware-integrated telemetry and emergency response network engineered to address the critical latency and false-alarm limitations of traditional software-only SOS notification applications.

## Key Features
- **Spatial Tracking & Relative Vector Mapping**: Computes continuous Haversine distance and spherical bearing vectors using dedicated hardware GPS nodes (NEO-6M), plotted in real-time onto spatial radar rings.
- **Multi-Modal Incident Verification**: Streams live biosensor telemetry (cardiovascular pulse / BPM via ADS1115 ADC), acoustic analysis (INMP441 I2S microphone), and real-time Haar Cascade facial bounding box detection.
- **Bidirectional Hardware Control**: Enables incident dispatchers and police consoles to verify emergency distress, remotely trigger emergency warnings, and reset false alarms.
- **Central Dispatch Portal**: Flask web dashboard for real-time responder monitoring, alert escalation, and telemetry visualization.

## Project Structure
- `app.py`: Flask web portal and REST/telemetry endpoint backend.
- `hardware.py`: Multi-threaded hardware monitor threads for audio, camera/face detection, sensors, and distress buttons.
- `config.py`: Port, pin, calibration, and streaming configurations.
- `HerGuard_Patent_Defense.md`: Technical documentation and novel claim defenses detailing structural distinctions over standard circular geofencing systems.

## Getting Started

1. **Install requirements**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the console**:
   ```bash
   python app.py
   ```

3. Open the police/dispatch portal at `http://localhost:5000`.
