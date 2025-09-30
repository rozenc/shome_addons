FROM debian:bullseye

RUN apt update && apt install -y \
    python3 \
    python3-pip \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    build-essential

RUN pip3 install pyaudio numpy paho-mqtt

COPY listener.py /listener.py

CMD ["python3", "/listener.py"]
