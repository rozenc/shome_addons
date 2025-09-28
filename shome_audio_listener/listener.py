#!/usr/bin/env python3
import os
import json
import time
import subprocess

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
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Test kaydı başarısız: {e}")

def main():
    audio_device = get_audio_device()
    log_ascii_banner(audio_device)
    test_recording(audio_device)
    print("[INFO] Dinleyici modülü hazır. Melodi tanıma bekleniyor...")

    # Buraya gerçek dinleme ve analiz mantığı eklenecek
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()