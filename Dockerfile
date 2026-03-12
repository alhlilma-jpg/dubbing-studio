FROM python:3.11-slim

# تثبيت ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 7860
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--timeout", "120", "--workers", "1"]
