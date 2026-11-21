# Response to Patent Examination: Technical Distinctions and Algorithmic Specifications of HerGuard Central

This submission addresses the two specific technical inquiries regarding the novelty, inventive step, and functional differences of HerGuard Central.

---

## Question 1: Functional and Structural Distinctions of the Volunteer Dashboard Over 112 India SHOUT

*Query: A precise technical description of how the Volunteer Dashboard's location-matching, verification, and dispatch logic differs functionally from the publicly documented 112 India SHOUT feature.*

The HerGuard Central platform does not operate like 112 India SHOUT. SHOUT is a software-only smartphone layer built around passive notifications. HerGuard Central is a hardware-integrated telemetry network. The functional differences span three specific operational areas:

### 1. Spatial Tracking & Relative Vector Mapping (vs. Static Circular Geofencing)

112 SHOUT pulls GPS coordinates from a victim's smartphone OS. It draws a fixed radial boundary (e.g., a 500m geofence) and broadcasts a mass push notification to all phones inside that circle. It cannot calculate direction of approach, relative closure speed, or directional vectors between the victim and individual responders.

HerGuard bypasses mobile OS geofencing entirely. Each victim node uses a dedicated hardware GPS module (NEO-6M) linked directly to an embedded processor. The server ingests raw coordinate streams and calculates exact geographic vectors using the Haversine formula and spherical bearing math:

```
Distance:
d = 2r · arcsin( sqrt( sin²((φ₂ - φ₁)/2) + cos(φ₁) · cos(φ₂) · sin²((λ₂ - λ₁)/2) ) )

Bearing:
θ = atan2( sin(λ₂ - λ₁) · cos(φ₂),  cos(φ₁) · sin(φ₂) - sin(φ₁) · cos(φ₂) · cos(λ₂ - λ₁) )
```

where φ represents latitude in radians, λ represents longitude in radians, and r is Earth's mean radius (6,371 km). 

The backend runs these calculations continuously across all active hardware nodes. The resulting polar vectors are plotted onto a live spatial radar grid with discrete distance bands at 100m, 200m, 300m, and 400m. 

Crucially, HerGuard displays all nearby active volunteers on the grid immediately. SHOUT only renders a responder after that individual manually accepts the broadcast on their phone.

### 2. Multi-Modal Incident Verification (vs. Administrative Pre-Registration)

112 SHOUT verifies identity only once—when a volunteer signs up using an Aadhaar card or government ID. When an SOS alert occurs, SHOUT has zero visibility into what is physically happening. It cannot verify whether an alert is real, accidental, or malicious.

HerGuard streams live multi-sensor telemetry straight from the victim's hardware node to the dashboard over WebSocket/REST channels:
* Live cardiovascular pulse waveform and real-time BPM from an ADS1115 ADC.
* Instantaneous acoustic noise levels and spectral frequency data from an INMP441 I2S microphone.
* Real-time 640×480 MJPEG video with bounding boxes from an on-device Haar Cascade face detector.

This setup allows a console operator to verify distress before dispatching volunteers. If the subject's pulse is resting (65 BPM), the audio is silent, and no faces are present, the operator can dismiss the alert immediately as a false alarm.

### 3. Bidirectional Hardware Control Topology (vs. One-Way Mobile Push)

112 SHOUT is strictly one-way: Phone presses SOS -> Server pushes notification -> Volunteer accepts -> Phone numbers swap. The dispatcher cannot control the victim's phone or inspect its hardware status.

HerGuard uses bidirectional REST endpoints. A dashboard operator can send hardware-level override instructions back to the deployed IoT node:
* Remotely trigger an emergency state if telemetry looks dangerous.
* Reset a triggered node back to resting state after false-alarm confirmation.
* Switch camera and audio streams on or off to preserve bandwidth and battery.
* Clear or download the on-device JPEG screenshot buffer (50-frame FIFO cache).
* Update the physical SSD1306 OLED screen on the victim's wrist between `[ RESTING ]` and `!! DANGER !!` modes.

---

## Question 2: Algorithmic Processing Specifications and Prior Art Distinctions

*Query: Confirmation of any algorithmic processing applied to the heart-rate, audio, or image data (e.g., automatic/threshold-based distress detection), and unique points over existing women safety patents.*

HerGuard does not use basic static volume or pulse limits. In real-world environments, static thresholds fail: loud traffic trips a microphone, and jogging trips a heart-rate monitor. We implemented multi-stage digital signal conditioning, frequency analysis, and a 2-of-3 temporal correlation fusion engine.

### On-Device Algorithmic Processing Pipelines

```
[Pulse Sensor] -> IIR Filter (α=0.90) -> DC Detrending -> Dynamic Peak Detection -> RMSSD HRV -> [Flag 1]
                                                                                                    |
[I2S Mic]      -> RMS Volume Check   -> 1024-pt FFT   -> Parabolic Refinement -> Energy Ratio -> [Flag 2] -> Fusion Gate
                                                                                                    |       (2 of 3 in 5s)
[Pi Camera]    -> Half-scale (320x240)-> Grayscale    -> Haar Cascade (5Hz)   -> Face Count   -> [Flag 3]         |
                                                                                                                  v
                                                                                                          [AUTO TRIGGER]
```

---

### Pipeline 1: Cardiovascular Conditioning & Adaptive Peak Detection

The analog pulse sensor connects to an ADS1115 16-bit ADC running at a 50Hz sampling rate (20ms intervals). Raw ADC readings pass through three conditioning stages:

*Stage 1: Low-Pass IIR Smoothing*
To strip out high-frequency electrical noise, muscle tremors, and the dicrotic notch, samples run through a single-pole IIR filter:

```
S[n] = 0.90 · S[n-1] + 0.10 · raw[n]
```

*Stage 2: DC Baseline Drift Subtraction*
Slow baseline drift caused by respiration and venous pooling is removed by subtracting a rolling 150-sample average (3-second window):

```
AC_signal[n] = S[n] - ( 1/150 · Σ S[n - k] )    for k = 0 to 149
```

*Stage 3: Dynamic Amplitude-Scaled Thresholding*
Instead of a fixed millivolt cutoff, the peak threshold scales with the user's pulse strength:

```
Threshold = max( 350,  0.40 · (AC_max - AC_baseline) )
```

*Peak Identification & Outlier-Immune BPM*
A heartbeat peak is registered when the signal slope shifts from positive to negative above the dynamic threshold:

```
AC[n-1] > Threshold  AND  AC[n-1] > AC[n-2]  AND  AC[n-1] > AC[n]
```

To prevent double-counting a single systolic peak, the algorithm enforces a 330ms refractory lockout period (capping maximum measurable heart rate at ~182 BPM). 

The output heart rate is calculated as the rolling median of the last 5 inter-beat intervals (ΔT):

```
BPM = 60 / median( ΔT₁, ΔT₂, ΔT₃, ΔT₄, ΔT₅ )
```

Using a median rather than a mean prevents a single missed beat or motion artifact from skewing the BPM reading.

---

### Pipeline 2: Stress-State Heart Rate Variability (HRV) Analysis

High heart rate alone is ambiguous: running produces 140 BPM, but so does acute terror. We separate them by calculating short-term Heart Rate Variability using the Root Mean Square of Successive Differences (RMSSD):

```
RMSSD = sqrt( 1/(N-1) · Σ (ΔT_{i+1} - ΔT_i)² )    for i = 1 to 4
```

* Exercise: Heart rate is elevated, but autonomic balance maintains natural beat-to-beat variability (RMSSD remains moderate/high).
* Panic/Fear: Sympathetic nerve activation floods the sinus node with norepinephrine, causing the heart to race with uniform spacing (RMSSD drops sharply).

The physiological distress flag trips only when both conditions are satisfied:

```
Physiological Flag = TRUE   if:  BPM > 115  AND  RMSSD < 18 ms
```

---

### Pipeline 3: Acoustic FFT, Parabolic Interpolation & Spectral Energy Ratio

Audio from the INMP441 I2S microphone is digitized at 16,000 Hz into 1,024-sample chunks (~64 ms per frame).

*Volume Gate (RMS Amplitude)*

```
RMS = sqrt( 1/1024 · Σ x[n]² )    for n = 0 to 1023
```

Frames must exceed an RMS noise floor of 0.01 before spectral analysis executes.

*FFT & Parabolic Sub-Bin Pitch Refinement*
A real-valued Fast Fourier Transform (rfft) maps the audio into 513 discrete frequency bins (15.625 Hz per bin). To get exact pitch without running a heavier 4,096-point FFT on the Pi Zero, we apply parabolic interpolation across the peak bin `k` and its immediate neighbors:

```
p = 0.5 · ( |X[k-1]| - |X[k+1]| ) / ( |X[k-1]| - 2·|X[k]| + |X[k+1]| )
f_exact = (k + p) · (16000 / 1024)
```

*Distress Band Energy Ratio*
Human screams concentrate acoustic energy in the 800 Hz – 3,500 Hz band (bins 52 through 224). Low-frequency background noise (engines, tire friction, wind) concentrates below 500 Hz. The algorithm computes the energy ratio between these bands:

```
E_distress = Σ |X[k]|²    for k ∈ [52, 224]
E_total    = Σ |X[k]|²    for k ∈ [0, 512]

Energy_Ratio = E_distress / E_total
```

```
Acoustic Flag = TRUE   if:  Energy_Ratio > 0.60  AND  RMS > 0.01  AND  accumulated over 30 frames (~1.9s)
```

A frame counter increments on match and decrements on mismatch, requiring ~1.9 seconds of sustained high-frequency energy. This filters out dropped items or brief horn honks.

---

### Pipeline 4: Decimated Face Detection & Visual Archiving

Running Haar Cascades on every 640×480 frame consumes 100% of the Pi Zero CPU and drops the video feed to 3 FPS. 

We solve this using spatial and temporal decimation:
1. Spatial: Incoming frames are scaled down by 50% (320×240) and converted to 8-bit grayscale, reducing pixel operations by 75%.
2. Temporal: Detection runs only on every 4th frame (5 Hz evaluation). Between detection frames, previously identified bounding boxes are retained and rendered onto the live 20 FPS MJPEG stream.

When a face is identified:
* A clean, full-resolution JPEG is saved to an in-memory 50-image circular buffer.
* The first frame captured at the exact moment of system trigger (`alert_start.jpg`) is pinned permanently to prevent overwrite during buffer rotation.

---

### Sensor Fusion Engine: 2-of-3 Temporal Gate

To eliminate false alarms caused by isolated sensor anomalies (e.g., dropping the device or jogging), the automatic trigger is governed by a multi-sensor coincidence rule:

```
AUTO_TRIGGER = TRUE   if at least TWO of the following conditions hold within a 5.0-second window:
  1. Physiological Flag is active (High BPM + Low RMSSD)
  2. Acoustic Flag is active (Sustained High Energy Ratio)
  3. Visual Flag is active (Face detected in close proximity)
```

If the user is attacked from behind and cannot scream, the camera (face detection) plus pulse sensor (heart spike) triggers the alarm. If the camera is covered inside a pocket, the audio scream plus heart spike triggers it. A single isolated sensor spike never triggers an alarm on its own.

A hardware panic button (3-second hold on GPIO 26) and dashboard remote trigger bypass this gate, providing a manual override.

---

## Detailed Prior Art Comparison Matrix

| Ref | Prior Art Architecture | HerGuard Central Structural & Algorithmic Advantages |
| :--- | :--- | :--- |
| **Ref 1** | GPS-only; purely voice-activated trigger. | Ref 1 fails if the victim is gagged, choked, or unable to speak. HerGuard adds autonomous physiological (PPG/HRV) and visual detection alongside GPS, triggering without requiring speech. |
| **Ref 2** | GPS + video; skin temperature sensing. | Skin temperature reacts to fear via cutaneous vasoconstriction on a delay of 3–5 minutes. Heart rate reacts within 1–2 seconds. HerGuard uses immediate cardiovascular response and adds an on-device OLED status interface. |
| **Ref 3** | Pressure + pulse; taser output; voice/fingerprint reset. | Taser mechanisms carry legal and liability restrictions in most jurisdictions. Ref 3 forces victim-side biometric deactivation, which fails if the victim is unconscious. HerGuard allows remote dispatcher reset and uses sensor fusion. |
| **Ref 4** | Piezoelectric glove; sweat/temp sensing; no GPS. | Ref 4 lacks GPS tracking, making victim localization impossible. Its glove form factor requires physical combat contact. HerGuard provides GPS vector tracking, video, audio, and volunteer dispatch. |
| **Ref 5** | Smart jewellery; audio/video/GPS recording. | Ref 5 is a passive recording device without a response system. HerGuard integrates a real-time volunteer dashboard, polar vector tracking, and bidirectional hardware control. |
| **Ref 6** | Ride-hailing gender risk prediction algorithm. | Ref 6 is a software-only metadata classifier for ride orders. It has no wearable hardware, no real-time physiological sensing, and no acoustic analysis. |
| **Ref 7** | Bra sensor; acoustic clapping trigger; cloud deep learning emotion recognition. | Clapping requires free arm movement, which fails during physical restraint. Cloud deep learning introduces latency and fails without cellular data. HerGuard uses on-device deterministic signal processing (IIR, RMSSD, FFT) running locally on low-power hardware without cloud dependency. |
