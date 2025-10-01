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
ENABLE_NOTE_DETECTION = os.getenv("ENABLE_NOTE_DETECTION", "true").lower() == "true"
NOTE_SENSITIVITY = float(os.getenv("NOTE_SENSITIVITY", "5.0"))  # Daha hassas
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "shome")
MQTT_PASS = os.getenv("MQTT_PASS", "a")
MQTT_TOPIC = "shome/devices/sHome-Listener"

# 🎚️ Ses parametreleri
CHUNK = 2048  # FFT için daha büyük chunk
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

# 🎼 GELİŞTİRİLMİŞ FFT ile nota tahmini
def detect_note_from_fft(data):
    try:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if samples.size < 1024:
            return None

        # Hanning window daha iyi sonuç verir
        window = np.hanning(len(samples))
        windowed_samples = samples * window

        # FFT hesapla
        fft = np.fft.rfft(windowed_samples)
        freqs = np.fft.rfftfreq(len(windowed_samples), 1.0 / RATE)
        magnitudes = np.abs(fft)
        
        # Gürültü eşiğini dinamik olarak belirle
        magnitude_threshold = np.max(magnitudes) * 0.1  # Daha düşük eşik
        
        # Tüm peak'leri bul
        peak_indices = np.where(magnitudes > magnitude_threshold)[0]
        
        if len(peak_indices) == 0:
            return None
        
        # En güçlü peak'i bul
        main_peak_index = peak_indices[np.argmax(magnitudes[peak_indices])]
        peak_freq = freqs[main_peak_index]

        # Frekans aralığını genişlet
        if peak_freq < 30 or peak_freq > 4000:  # Daha geniş aralık
            return None

        # En yakın notayı bul
        closest_note = min(PIANO_NOTES, key=lambda x: abs(x[1] - peak_freq))
        freq_diff = abs(closest_note[1] - peak_freq)
        
        # Cent cinsinden farkı hesapla (daha hassas)
        cents_diff = 1200 * np.log2(peak_freq / closest_note[1]) if closest_note[1] > 0 else 999
        
        # Daha geniş tolerans
        if abs(cents_diff) > (NOTE_SENSITIVITY * 50):  # 50 cent = yarım perde
            return None
            
        # DEBUG: Frekans ve nota bilgisini yazdır
        print(f"[DEBUG] Frekans: {peak_freq:.1f}Hz, Nota: {closest_note[0]}, Fark: {cents_diff:.1f} cent")
            
        return closest_note[0]
        
    except Exception as e:
        print(f"[FFT_ERROR] {e}")
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
    level_history = deque(maxlen=10)  # Daha kısa history
    last_detection_time = 0
    cooldown_period = 1  # Daha kısa cooldown
    consecutive_detections = 0
    
    # A4 notasını (440 Hz) özellikle kontrol etmek için
    TARGET_NOTE = "A4"
    target_note_detected = False

    print("[START] Çamaşır makinesi melodisi dinleniyor...")
    print(f"[CONFIG] Eşik: {RMS_THRESHOLD}, Kazanç: {MIC_GAIN}, Nota Tespiti: {ENABLE_NOTE_DETECTION}")
    print(f"[TARGET] Hedef nota: {TARGET_NOTE} (440 Hz)")

    # 🔍 Basit melodi tespiti fonksiyonu
    def detect_melody_pattern(levels, current_level):
        if len(levels) < levels.maxlen:
            return False
            
        recent_levels = list(levels)
        
        # Basit varyans hesaplama
        level_variance = np.var(recent_levels)
        
        # Tepe noktası sayısını hesapla
        peaks = 0
        for i in range(1, len(recent_levels)-1):
            if recent_levels[i] > recent_levels[i-1] and recent_levels[i] > recent_levels[i+1]:
                peaks += 1
        
        # DEBUG: Desen analizini yazdır
        if len(recent_levels) >= 5:
            print(f"[PATTERN] Varyans: {level_variance:.0f}, Tepe: {peaks}")
        
        # Daha basit desen tespiti
        return level_variance > 50000 or peaks >= 2

    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = get_rms(data) * MIC_GAIN
            current_time = time.time()

            # Seviye eşiğini aşma kontrolü
            if rms < RMS_THRESHOLD:
                consecutive_detections = 0
                target_note_detected = False
                continue

            # Nota tespiti
            detected_note = None
            if ENABLE_NOTE_DETECTION:
                detected_note = detect_note_from_fft(data)
                
                # Hedef nota (A4) tespit edildi mi?
                if detected_note == TARGET_NOTE:
                    if not target_note_detected:
                        print(f"[TARGET_NOTE] 🎯 {TARGET_NOTE} (440 Hz) ALGILANDI! 🎯")
                        target_note_detected = True
                    
                    consecutive_detections += 1
                    
                    # Ardışık tespit sayısına göre işlem yap
                    if consecutive_detections >= 3:  # 3 kere üst üste tespit
                        print(f"[MELODY] 🎵 {detected_note} - Güçlü algılama! (Seviye: {rms:.2f})")
                        mqttc.publish(MQTT_TOPIC, json.dumps({
                            "type": "target_note_detected",
                            "note": detected_note,
                            "level": float(rms),
                            "consecutive": consecutive_detections,
                            "timestamp": current_time
                        }))
                        last_detection_time = current_time
                else:
                    consecutive_detections = 0
                    target_note_detected = False
                    
                    # Diğer notaları da raporla
                    if detected_note:
                        print(f"[NOTE] {detected_note} (Seviye: {rms:.2f})")
                        mqttc.publish(MQTT_TOPIC, json.dumps({
                            "type": "note_detected", 
                            "note": detected_note,
                            "level": float(rms),
                            "timestamp": current_time
                        }))
            
            # Melodi deseni tespiti (nota tespiti olmasa bile)
            is_melody = detect_melody_pattern(level_history, rms)
            
            if is_melody and (current_time - last_detection_time) > cooldown_period:
                print(f"[MELODY] 🔔 Desen tespit edildi! (Seviye: {rms:.2f})")
                mqttc.publish(MQTT_TOPIC, json.dumps({
                    "type": "melody_pattern",
                    "level": float(rms),
                    "pattern": True,
                    "timestamp": current_time
                }))
                last_detection_time = current_time

            # Seviyeyi her zaman history'e ekle ve MQTT'ye gönder
            level_history.append(rms)
            print(f"[LEVEL] {rms:.2f}")

        except IOError as e:
            # Overflow hataları normaldir, sessizce devam et
            continue
        except Exception as e:
            print(f"[ERROR] Akış okuma hatası: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()