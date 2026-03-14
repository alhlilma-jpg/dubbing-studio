FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تحميل النموذج أثناء البناء
RUN python3 -c "
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
TTS('tts_models/multilingual/multi-dataset/xtts_v2')
print('✅ Model cached!')
"

COPY app.py .
EXPOSE 8000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--timeout", "300", "--workers", "1", "--preload"]
