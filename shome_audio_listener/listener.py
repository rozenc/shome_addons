import os
os.environ['PYAUDIO_IGNORE_ALSA_PLUGINS'] = '1'

import pyaudio
import numpy as np
import json
import time
import paho.mqtt.client as mqtt
from collections import deque

# 🔧 Ortam değişkenleri
DEVICE_INDEX = int(os.getenv("DEVICE_INDEX", "-1"))
MIC_GAIN = float(os.getenv("MIC_GAIN", "1.5"))
RMS_THRESHOLD = int(os.getenv("RMS_THRESHOLD", "1000"))
ENABLE_NOTE_DETECTION = os.getenv("ENABLE_NOTE_DETECTION", "false").lower() == "true"
NOTE_SENSITIVITY = float(os.getenv("NOTE_SENSITIVITY", "20.0"))  # Artırıldı
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

# 📐 Geliştirilmiş RMS hesaplama
def get_rms(data):
    try:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if samples.size == 0 or np.all(samples == 0):
            return 0.0
        rms = np.sqrt(np.mean(samples**2))
        return rms if not np.isnan(rms) else 0.0
    except:
        return 0.0

# 🎼 Geliştirilmiş FFT ile nota tahmini
def detect_note_from_fft(data):
    try:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if samples.size < 1024:
            return None

        # Pencereleme için Hamming window
        window = np.hamming(len(samples))
        windowed_samples = samples * window

        fft = np.fft.rfft(windowed_samples)
        freqs = np.fft.rfftfreq(len(windowed_samples), 1.0 / RATE)
        magnitude = np.abs(fft)
        
        # Gürültüyü filtrele
        magnitude_threshold = np.max(magnitude) * 0.3
        peak_indices = np.where(magnitude > magnitude_threshold)[0]
        
        if len(peak_indices) == 0:
            return None
            
        peak_index = peak_indices[0]
        peak_freq = freqs[peak_index]

        if peak_freq < 50 or peak_freq > 2000:
            return None

        closest = min(PIANO_NOTES, key=lambda x: abs(x[1] - peak_freq))
        freq_diff = abs(closest[1] - peak_freq)
        
        # NOTA_SENSITIVITY değeri daha yüksek, daha toleranslı
        if freq_diff > NOTE_SENSITIVITY:
            return None
            
        return closest[0]
    except Exception as e:
        return None

def list_audio_devices():
    """Mevcut ses cihazlarını listele"""
    p = pyaudio.PyAudio()
    print("=" * 60)
    print("Kullanılabilir Ses Giriş Cihazları:")
    print("=" * 60)
    
    input_devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            input_devices.append((i, info['name'], info['maxInputChannels']))
            print(f"Index: {i}, Name: {info['name']}, Channels: {info['maxInputChannels']}")
    
    p.terminate()
    print("=" * 60)
    return input_devices

# 🚀 Ana döngü
def main():
    # Önce cihazları listele
    input_devices = list_audio_devices()
    
    if not input_devices:
        print("[ERROR] Hiçbir ses giriş cihazı bulunamadı!")
        return
    
    p = pyaudio.PyAudio()
    
    # Stream konfigürasyonu
    stream_config = {
        'format': pyaudio.paInt16,
        'channels': 1,
        'rate': RATE,
        'input': True,
        'frames_per_buffer': CHUNK,
        'input_device_index': DEVICE_INDEX
    }
    
    try:
        stream = p.open(**stream_config)
        print(f"[SUCCESS] Ses akışı açıldı (Cihaz: {DEVICE_INDEX})")
    except Exception as e:
        print(f"[ERROR] Akış açılamadı: {e}")
        print("[INFO] Varsayılan cihaz deneniyor...")
        try:
            stream_config['input_device_index'] = None
            stream = p.open(**stream_config)
            print("[SUCCESS] Varsayılan cihazla akış açıldı")
        except Exception as e2:
            print(f"[FATAL] Hiçbir cihazla akış açılamadı: {e2}")
            return

    # MQTT istemcisi
    try:
        mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except:
        mqttc = mqtt.Client()
    
    mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
    
    try:
        mqttc.connect(MQTT_HOST, MQTT_PORT)
        print(f"[MQTT] {MQTT_HOST}:{MQTT_PORT} bağlantısı kuruldu")
    except Exception as e:
        print(f"[MQTT_ERROR] Bağlantı hatası: {e}")

    # 📊 Ses analizi için değişkenler
    level_history = deque(maxlen=20)
    last_detection_time = 0
    cooldown_period = 2
    continuous_high_level_start = 0
    continuous_detection_threshold = 2  # 2 saniye boyunca yüksek seviye

    print("[START] Çamaşır makinesi melodisi dinleniyor...")
    print(f"[CONFIG] Eşik: {RMS_THRESHOLD}, Kazanç: {MIC_GAIN}, Nota Tespiti: {ENABLE_NOTE_DETECTION}")

    # 🔍 Geliştirilmiş melodi tespiti fonksiyonu
    def detect_melody_pattern(levels, current_level, current_time):
        level_history.append(current_level)
        
        # Yöntem 1: Seviye dalgalanmaları (orijinal yöntem)
        if len(level_history) >= level_history.maxlen:
            recent_levels = list(level_history)
            level_variance = np.var(recent_levels)
            
            if level_variance > 100000:
                peaks = 0
                for i in range(1, len(recent_levels)-1):
                    if recent_levels[i] > recent_levels[i-1] and recent_levels[i] > recent_levels[i+1]:
                        peaks += 1
                if peaks >= 3:
                    return True

        # Yöntem 2: Sürekli yüksek seviye
        if current_level >= RMS_THRESHOLD:
            if continuous_high_level_start == 0:
                continuous_high_level_start = current_time
            elif current_time - continuous_high_level_start >= continuous_detection_threshold:
                return True
        else:
            continuous_high_level_start = 0

        return False

    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = get_rms(data) * MIC_GAIN
            current_time = time.time()

            # Cooldown kontrolü
            if current_time - last_detection_time < cooldown_period:
                continue

            # Seviye eşiğini aşma kontrolü
            if rms < RMS_THRESHOLD:
                continuous_high_level_start = 0  # Sıfırla
                continue

            # Melodi deseni tespiti
            is_melody = detect_melody_pattern(level_history, rms, current_time)
            
            if ENABLE_NOTE_DETECTION:
                note = detect_note_from_fft(data)
                if note:
                    print(f"[MELODY] 🎵 {note} (Seviye: {rms:.2f})")
                    mqttc.publish(MQTT_TOPIC, json.dumps({
                        "type": "melody_detected",
                        "note": note,
                        "level": float(rms),
                        "pattern": is_melody,
                        "timestamp": current_time
                    }))
                    last_detection_time = current_time
                elif is_melody:
                    # Nota tespit edilemese bile melodi deseni varsa
                    print(f"[MELODY] 🔔 Desen tespit edildi! (Seviye: {rms:.2f})")
                    mqttc.publish(MQTT_TOPIC, json.dumps({
                        "type": "melody_pattern",
                        "level": float(rms),
                        "timestamp": current_time
                    }))
                    last_detection_time = current_time
            else:
                if is_melody:
                    print(f"[MELODY] 🔔 Desen tespit edildi! (Seviye: {rms:.2f})")
                    mqttc.publish(MQTT_TOPIC, json.dumps({
                        "type": "melody_pattern",
                        "level": float(rms),
                        "timestamp": current_time
                    }))
                    last_detection_time = current_time
                else:
                    print(f"[LEVEL] {rms:.2f}")
                    mqttc.publish(MQTT_TOPIC, json.dumps({
                        "level": float(rms),
                        "timestamp": current_time
                    }))

        except IOError as e:
            # Overflow hataları normaldir, sessizce devam et
            continue
        except Exception as e:
            print(f"[ERROR] Akış okuma hatası: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()