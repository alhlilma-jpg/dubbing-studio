FROM python:3.11-slim

# تثبيت ffmpeg والأدوات
RUN apt-get update && \
    apt-get install -y ffmpeg git wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المكتبات أولاً (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تحميل نموذج XTTS v2 مسبقاً أثناء البناء
# هذا يمنع تحميله عند كل إعادة تشغيل
RUN python3 -c "
from TTS.api import TTS
import os
os.environ['COQUI_TOS_AGREED'] = '1'
print('Downloading XTTS v2 model...')
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2')
print('Model downloaded successfully!')
"

COPY . .

EXPOSE 8000
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "300", \
     "--workers", "1", \
     "--preload"]
