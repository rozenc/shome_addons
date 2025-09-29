#!/usr/bin/env python3
import json
import time
import numpy as np
import sounddevice as sd

CONFIG_PATH = "/data/options.json"

def get_audio_device():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("audio_device", "plughw:1,2")
    except:
        return "plughw:1,2"

def log_ascii_banner(device):
    print(f"""
╔══════════════════════════════════════╗
║  🎧 sHome Audio Listener Başladı     ║
║  Aktif Ses Cihazı: {device:<20} ║
╚══════════════════════════════════════╝
""")

def print_level_bar(rms):
    """RMS değerini terminalde bar olarak göster"""
    bar_len = int(rms * 50)
    bar = "#" * bar_len
    print(f"[LEVEL] |{bar:<50}| {rms:.3f}")

def main():
    device = get_audio_device()
    log_ascii_banner(device)

    duration = 0.2  # kısa aralıklarla örnekleme
    fs = 44100

    while True:
        try:
            audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device)
            sd.wait()
            audio = audio.flatten()
            rms = np.sqrt(np.mean(audio**2))
            print_level_bar(rms)
            time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] Mikrofon okunamadı: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
