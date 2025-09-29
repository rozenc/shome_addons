FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libportaudio2 \
    libportaudiocpp0 \
    libasound2-dev \
    libasound2-plugins \
    alsa-utils \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir sounddevice numpy scipy paho-mqtt

COPY run.sh /run.sh
COPY listener.py /listener.py

RUN chmod +x /run.sh

CMD ["/run.sh"]
