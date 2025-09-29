#!/usr/bin/env python3
import os
import json
import time
import subprocess
import numpy as np
import sounddevice as sd

CONFIG_PATH = "/data/options.json"

def get_audio_device():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("audio_device", "default")
    except Exception as e:
        print(f"[ERROR] Config okunamadı: {e}")
        return "default"

def log_ascii_banner(device):
    banner = f"""
    ╔══════════════════════════════════════╗
    ║  🎧 sHome Audio Listener Başladı     ║
    ║  Aktif Ses Cihazı: {device:<20} ║
    ╚══════════════════════════════════════╝
    """
    print(banner)

def test_recording(device):
    print(f"[INFO] '{device}' cihazından kısa test kaydı başlatılıyor...")
    try:
        subprocess.run([
            "arecord",
            "-D", device,
            "-d", "2",
            "-f", "cd",
            "/dev/null"
        ], check=True)
        print("[INFO] Test kaydı başarılı.")
    except FileNotFoundError:
        print("[ERROR] 'arecord' komutu bulunamadı. Dockerfile'a alsa-utils eklenmeli.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Test kaydı başarısız: {e}")

def detect_note(device):
    try:
        duration = 1
        fs = 44100
        audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device)
        sd.wait()
        audio = audio.flatten()
        fft = np.fft.fft(audio)
        freqs = np.fft.fftfreq(len(fft), 1/fs)
        idx = np.argmax(np.abs(fft[:len(fft)//2]))
        freq = freqs[idx]
        print(f"[LOG] Algılanan frekans: {freq:.2f} Hz")

        notes = {
            261.63: "C4", 293.66: "D4", 329.63: "E4",
            349.23: "F4", 392.00: "G4", 440.00: "A4", 493.88: "B4"
        }
        closest = min(notes.keys(), key=lambda x: abs(x - freq))
        print(f"[LOG] Yakalanan nota: {notes[closest]} 🎵")

    except Exception as e:
        print(f"[ERROR] Nota algılama başarısız: {e}")

def main():
    audio_device = get_audio_device()
    log_ascii_banner(audio_device)
    test_recording(audio_device)
    print("[INFO] Dinleyici modülü hazır. Melodi tanıma başlıyor...")

    while True:
        detect_note(audio_device)
        time.sleep(5)

if __name__ == "__main__":
    main()
