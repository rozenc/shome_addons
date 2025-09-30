import pyaudio
import numpy as np
import json
import os
import time
import paho.mqtt.client as mqtt

DEVICE_INDEX = int(os.getenv("DEVICE_INDEX", "-1"))
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "shome")
MQTT_PASS = os.getenv("MQTT_PASS", "a")
MQTT_TOPIC = "shome/devices/sHome-Listener"

CHUNK = 1024
RATE = 44100
THRESHOLD = 500

def get_rms(data):
    samples = np.frombuffer(data, dtype=np.int16)
    rms = np.sqrt(np.mean(samples**2))
    return rms

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

    print("[START] Listening via PulseAudio...")
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = get_rms(data)
            print(f"[LEVEL] {rms:.2f}")
            if rms > THRESHOLD:
                mqttc.publish(MQTT_TOPIC, json.dumps({
                    "level": rms,
                    "timestamp": time.time()
                }))
                print("[MQTT] Triggered")
        except Exception as e:
            print(f"[ERROR] Stream read failed: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
