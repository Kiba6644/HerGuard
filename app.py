import time
import os
import sys
import collections
from datetime import datetime
from flask import Flask, render_template, Response, jsonify, request, send_from_directory

# Import local modules
import config
from hardware import system_state, AudioMonitor, SensorMonitor, CameraMonitor, ButtonMonitor

# Initialize Flask app
app = Flask(__name__, 
            template_folder=os.path.join(config.PROJECT_ROOT, "templates"),
            static_folder=config.STATIC_DIR)

# Ensure folders exist
os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)


@app.route('/')
def index():
    """Renders the main Police Portal dashboard."""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """
    Returns the real-time status of the system, including
    BPM, mic frequency, amplitude, state, active duration,
    and the list of all captured face screenshots.
    """
    # Fetch list of face screenshots from memory cache sorted descending
    with system_state.lock:
        screenshot_files = [k for k in system_state.screenshots_cache.keys() if k.startswith("face_")]
        screenshot_files.sort(reverse=True)

    # Get hardware telemetry dict
    status_data = system_state.get_status_dict()
    status_data["screenshots"] = screenshot_files
    
    return jsonify(status_data)


@app.route('/api/trigger', methods=['POST'])
def force_trigger():
    """Remotely triggers the warning state on the device."""
    triggered = system_state.trigger(source="remote")
    if triggered:
        return jsonify({"status": "success", "message": "System triggered remotely"})
    return jsonify({"status": "ignored", "message": "System is already in triggered state"})


@app.route('/api/reset', methods=['POST'])
def reset_system():
    """Resets the safety alarm state back to resting/safe."""
    reset_ok = system_state.reset()
    if reset_ok:
        # Delete screenshots on false alarm reset to free up memory (Optional: but keeping screenshots for police review is nice.
        # User said "which puts the system back to its normal state". Let's keep screenshots but reset local counter).
        return jsonify({"status": "success", "message": "System reset to resting state successfully"})
    return jsonify({"status": "ignored", "message": "System was already resting"})


@app.route('/api/delete_screenshots', methods=['POST'])
def delete_screenshots():
    """Deletes all saved face screenshots from memory to clear history."""
    try:
        with system_state.lock:
            system_state.screenshots_cache.clear()
            system_state.captured_faces_count = 0
        return jsonify({"status": "success", "message": "All memory cached screenshots cleared successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to delete screenshots: {str(e)}"}), 500


@app.route('/static/screenshots/<filename>')
def serve_cached_screenshot(filename):
    """Serves captured face images directly from the memory cache."""
    with system_state.lock:
        img_bytes = system_state.screenshots_cache.get(filename)
    if img_bytes:
        return Response(img_bytes, mimetype='image/jpeg')
    return "Image not found", 404


def generate_video_stream():
    """Generates the live camera feed MJPEG byte frames."""
    # Pre-generate a 'Camera Offline' placeholder frame to stream during resting state
    import cv2
    import numpy as np
    
    offline_img = np.zeros((config.CAM_HEIGHT, config.CAM_WIDTH, 3), dtype=np.uint8)
    # Draw sleek dark grey gradient background or visual elements
    offline_img[:, :] = (18, 14, 13) # Dark matching glassmorphic panel color
    cv2.putText(offline_img, "CAMERA OFFLINE", (config.CAM_WIDTH//2 - 130, config.CAM_HEIGHT//2 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2, cv2.LINE_AA)
    cv2.putText(offline_img, "System in safe resting state", (config.CAM_WIDTH//2 - 150, config.CAM_HEIGHT//2 + 20), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (70, 70, 70), 1, cv2.LINE_AA)
    ret, jpeg_offline = cv2.imencode('.jpg', offline_img)
    offline_bytes = jpeg_offline.tobytes() if ret else b''

    while True:
        if system_state.state == "triggered" and system_state.latest_frame is not None:
            # Send live frame from camera thread
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + system_state.latest_frame + b'\r\n')
            time.sleep(1.0 / config.CAM_FPS)
        else:
            # Send offline placeholder image at a very slow pace to conserve bandwidth/CPU
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + offline_bytes + b'\r\n')
            time.sleep(0.3)


@app.route('/video_feed')
def video_feed():
    """Endpoint serving the live MJPEG camera feed."""
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def generate_audio_stream():
    """
    Generates a chunked live WAV audio stream from the microphone.
    Appends an infinite WAV format header on connect, and yields raw PCM binary chunks.
    """
    # WAV Header (PCM, 16000Hz, Mono, 16-bit). We specify 0xFFFFFFFF (unlimited) sizes.
    header = bytearray(44)
    header[0:4] = b'RIFF'
    header[4:8] = (0xFFFFFFFF).to_bytes(4, 'little')  # Chunk size
    header[8:12] = b'WAVE'
    header[12:16] = b'fmt '
    header[16:20] = (16).to_bytes(4, 'little')        # Subchunk1Size
    header[20:22] = (1).to_bytes(2, 'little')         # AudioFormat (1=PCM)
    header[22:24] = (config.AUDIO_CHANNELS).to_bytes(2, 'little')
    header[24:28] = (config.AUDIO_SAMPLE_RATE).to_bytes(4, 'little')
    header[28:32] = (config.AUDIO_SAMPLE_RATE * config.AUDIO_CHANNELS * 2).to_bytes(4, 'little') # ByteRate
    header[32:34] = (config.AUDIO_CHANNELS * 2).to_bytes(2, 'little')  # BlockAlign
    header[34:36] = (16).to_bytes(2, 'little')         # BitsPerSample (16-bit)
    header[36:40] = b'data'
    header[40:44] = (0xFFFFFFFF).to_bytes(4, 'little')  # Subchunk2Size

    # Send WAV header immediately
    yield bytes(header)

    # Stream real-time mic buffer data
    while True:
        if system_state.state == "triggered":
            if len(system_state.audio_queue) > 0:
                # Lag-Skipping: If queue has accumulated blocks (network latency),
                # instantly skip to the absolute latest 2 blocks to maintain zero lag!
                while len(system_state.audio_queue) > 2:
                    system_state.audio_queue.popleft()
                chunk = system_state.audio_queue.popleft()
                yield chunk
            else:
                time.sleep(0.01)
        else:
            # Yield silence chunk if resting to immediately mute the stream on the frontend
            # size matches chunk size (1024 samples * 2 bytes/sample)
            yield b'\x00' * (config.AUDIO_CHUNK_SIZE * 2)
            time.sleep(0.04) # Sleep matches chunk duration to pace stream


@app.route('/audio_feed')
def audio_feed():
    """Endpoint serving live WAV audio feed."""
    return Response(generate_audio_stream(), mimetype='audio/wav')


# Launch hardware threads on startup
audio_monitor = AudioMonitor()
sensor_monitor = SensorMonitor()
camera_monitor = CameraMonitor()
button_monitor = ButtonMonitor()

audio_monitor.start()
sensor_monitor.start()
camera_monitor.start()
button_monitor.start()

print("Hardware threads started successfully.")

if __name__ == '__main__':
    # Run the web server
    print(f"Starting Women's Safety System Dashboard on http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
