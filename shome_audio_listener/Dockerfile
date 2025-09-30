FROM debian:bullseye

RUN apt update && apt install -y \
    python3 \
    python3-pip \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    pulseaudio \
    build-essential \
 && apt clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY listener.py .
CMD ["python3", "listener.py"]
