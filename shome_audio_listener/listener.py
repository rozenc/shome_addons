import sounddevice as sd
import numpy as np
import time
import paho.mqtt.client as mqtt

# 🎼 Sabitler
SAMPLERATE = 48000
CHANNELS = 1
DTYPE = 'int16'
AMPLITUDE_THRESHOLD = 10000
FREQ_TOLERANCE = 50
NOTE_FREQS = {
    'C#7': 2217.46,
    'E7': 2637.02,
    'B6': 1975.53,
    'A6': 1760.00,
    'F#6': 1479.98
}
NOTE_SEQUENCE = ['C#7', 'E7', 'B6', 'A6', 'F#6']
WINDOW_DURATION = 1
COOLDOWN_PERIOD = 10

note_state = {'index': 0, 'last_time': None, 'notes': []}
last_detection_time = None

# 🎧 Ses kaydı
def record_audio():
    audio = sd.rec(int(SAMPLERATE * 0.05), samplerate=SAMPLERATE, channels=CHANNELS, dtype=DTYPE)
    sd.wait()
    audio = audio.astype(np.float32)
    audio -= np.mean(audio)
    return audio

# 🎚️ Bant geçiş filtresi
def bandpass_filter(data):
    from scipy.signal import butter, lfilter
    nyq = 0.5 * SAMPLERATE
    low = 1400 / nyq
    high = 2700 / nyq
    b, a = butter(5, [low, high], btype='band')
    return lfilter(b, a, data)

# 🎶 Nota tanıma
def detect_notes(filtered_audio):
    fft_data = np.fft.fft(filtered_audio)
    fft_freqs = np.fft.fftfreq(len(fft_data), 1/SAMPLERATE)
    fft_magnitude = np.abs(fft_data)

    pos_mask = (fft_freqs > 1400) & (fft_freqs < 2700)
    fft_freqs = fft_freqs[pos_mask]
    fft_magnitude = fft_magnitude[pos_mask]

    detected = []
    for note, freq in NOTE_FREQS.items():
        mask = (fft_freqs >= freq - FREQ_TOLERANCE) & (fft_freqs <= freq + FREQ_TOLERANCE)
        if np.any(mask):
            max_mag = np.max(fft_magnitude[mask])
            if max_mag > AMPLITUDE_THRESHOLD:
                detected.append(note)
    return detected

# ✅ Melodi eşleşme
def match_sequence(detected_notes):
    global note_state, last_detection_time
    now = time.time()

    if last_detection_time and now - last_detection_time < COOLDOWN_PERIOD:
        return False

    if note_state['index'] == 0:
        if 'C#7' in detected_notes:
            note_state['index'] = 1
            note_state['last_time'] = now
            note_state['notes'] = ['C#7']
            print("[🎶] Başlangıç notası algılandı: C#7")
    else:
        expected = NOTE_SEQUENCE[note_state['index']]
        if expected in detected_notes:
            if now - note_state['last_time'] <= WINDOW_DURATION:
                note_state['index'] += 1
                note_state['last_time'] = now
                note_state['notes'].append(expected)
                print(f"[🎶] Sıradaki nota: {expected}")
            else:
                print("[⚠️] Zaman aşımı, sıfırlanıyor.")
                note_state = {'index': 0, 'last_time': None, 'notes': []}
        else:
            print("[❌] Beklenen nota yok, sıfırlanıyor.")
            note_state = {'index': 0, 'last_time': None, 'notes': []}

    if note_state['index'] == len(NOTE_SEQUENCE):
        print("[✅] Melodi tamamlandı!")
        note_state = {'index': 0, 'last_time': None, 'notes': []}
        last_detection_time = now
        return True

    return False

# 📡 MQTT gönderimi
def send_mqtt():
    client = mqtt.Client()
    client.connect("homeassistant.local", 1883, 60)
    client.publish("home/laundry/status", "done")
    client.disconnect()
    print("[📡] MQTT mesajı gönderildi: done")

# 🔁 Ana döngü
while True:
    try:
        audio = record_audio()
        filtered = bandpass_filter(audio)
        notes = detect_notes(filtered)
        if match_sequence(notes):
            send_mqtt()
            time.sleep(COOLDOWN_PERIOD)
        else:
            print("[🎧] Dinleniyor...")
        time.sleep(1)
    except Exception as e:
        print(f"[💥] Hata: {e}")
        time.sleep(5)
