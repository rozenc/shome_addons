import pyaudio
import numpy as np
import json
import os
import time
import paho.mqtt.client as mqtt

# 🔧 Ortam değişkenleri
DEVICE_INDEX = int(os.getenv("DEVICE_INDEX", "-1"))
MIC_GAIN = float(os.getenv("MIC_GAIN", "2.0"))
RMS_THRESHOLD = int(os.getenv("RMS_THRESHOLD", "500"))
ENABLE_NOTE_DETECTION = os.getenv("ENABLE_NOTE_DETECTION", "false").lower() == "true"
NOTE_SENSITIVITY = float(os.getenv("NOTE_SENSITIVITY", "1.0"))
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "shome")
MQTT_PASS = os.getenv("MQTT_PASS", "a")
MQTT_TOPIC = "shome/devices/sHome-Listener"

# 🎚️ Ses parametreleri
CHUNK = 1024
RATE = 44100

# 🎼 Piyano nota frekansları (A0–C8)
PIANO_NOTES = []
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
for i in range(21, 109):  # MIDI 21–108
    freq = 440.0 * (2 ** ((i - 69) / 12))
    name = NOTE_NAMES[i % 12] + str((i // 12) - 1)
    PIANO_NOTES.append((name, freq))

# 📐 RMS hesaplama (sade)
def get_rms(data):
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if samples.size == 0 or np.isnan(np.mean(samples)):
        return 0.0
    rms = np.sqrt(np.mean(samples**2))
    return rms

# 🎼 FFT ile nota tahmini (opsiyonel)
def detect_note_from_fft(data):
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return None

    fft = np.fft.fft(samples)
    freqs = np.fft.fftfreq(len(fft), 1.0 / RATE)
    magnitude = np.abs(fft)
    peak_index = np.argmax(magnitude[:len(magnitude)//2])
    peak_freq = abs(freqs[peak_index])

    if peak_freq < 20 or peak_freq > 5000:
        return None

    closest = min(PIANO_NOTES, key=lambda x: abs(x[1] - peak_freq))
    if abs(closest[1] - peak_freq) > NOTE_SENSITIVITY:
        return None
    return closest[0]

# 🚀 Ana döngü
def main():
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=RATE,
                        input=True,
                        input_device_index=DEVICE_INDEX,
                        frames_per_buffer=CHUNK)
    except Exception as e:
        print(f"[ERROR] Cannot open stream: {e}")
        return

    mqttc = mqtt.Client()
    mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
    mqttc.connect(MQTT_HOST, MQTT_PORT)

    print("[START] Listening via ALSA...")
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = get_rms(data) * MIC_GAIN

            if rms < RMS_THRESHOLD:
                continue

            if ENABLE_NOTE_DETECTION:
                note = detect_note_from_fft(data)
                if note:
                    print(f"[NOTE] {note} 🎹 (RMS: {rms:.2f})")
                    mqttc.publish(MQTT_TOPIC, json.dumps({
                        "note": note,
                        "level": rms,
                        "timestamp": time.time()
                    }))
            else:
                print(f"[LEVEL] {rms:.2f}")
                mqttc.publish(MQTT_TOPIC, json.dumps({
                    "level": rms,
                    "timestamp": time.time()
                }))
        except Exception as e:
            print(f"[ERROR] Stream read failed: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()