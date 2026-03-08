# =============================================================
# sl-Dubbing AI Server - Voice Cloning & SRT Sync Engine
# =============================================================
import os
import io
import re
import json
import uuid
import base64
import logging
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import soundfile as sf
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import pysrt
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

# TTS Imports
try:
    from TTS.api import TTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("TTS not available, using fallback")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS معدل للسماح بالوصول من GitHub Pages
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://sl-dubbing.github.io",
            "https://*.github.io",
            "http://localhost:*",
            "*"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///dubbing.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['OUTPUT_FOLDER'] = '/tmp/outputs'

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

db = SQLAlchemy(app)
mail = Mail(app)

# Create directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# =============================================================
# Voice Cloning Engine
# =============================================================
class VoiceCloningEngine:
    def __init__(self):
        self.tts_model = None
        self.model_loaded = False
        self.load_model()
    
    def load_model(self):
        try:
            if TTS_AVAILABLE:
                logger.info("Loading XTTS model...")
                self.tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
                self.model_loaded = True
                logger.info("XTTS model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
    
    def clone_voice(self, text, speaker_wav_path, language="ar", output_path=None):
        if not self.model_loaded or not TTS_AVAILABLE:
            return self._fallback_tts(text, language, output_path)
        
        try:
            if output_path is None:
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"cloned_{uuid.uuid4()}.wav")
            
            self.tts_model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav_path,
                language=language,
                file_path=output_path
            )
            
            return output_path
        except Exception as e:
            logger.error(f"Voice cloning error: {e}")
            return self._fallback_tts(text, language, output_path)
    
    def _fallback_tts(self, text, language, output_path):
        try:
            from gtts import gTTS
            if output_path is None:
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"fallback_{uuid.uuid4()}.mp3")
            
            tts = gTTS(text=text, lang=language[:2], slow=False)
            tts.save(output_path)
            return output_path
        except:
            return None

voice_engine = VoiceCloningEngine()

# =============================================================
# SRT Processor with Time Sync
# =============================================================
class SRTDubbingProcessor:
    def __init__(self):
        self.sample_rate = 24000
    
    def parse_srt(self, srt_content):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
                f.write(srt_content)
                temp_path = f.name
            
            subs = pysrt.open(temp_path, encoding='utf-8')
            os.unlink(temp_path)
            
            items = []
            for sub in subs:
                items.append({
                    'index': sub.index,
                    'start': self._time_to_ms(sub.start),
                    'end': self._time_to_ms(sub.end),
                    'duration': self._time_to_ms(sub.end) - self._time_to_ms(sub.start),
                    'text': sub.text.replace('\\n', ' ').strip()
                })
            return items
        except Exception as e:
            logger.error(f"SRT parse error: {e}")
            return []
    
    def _time_to_ms(self, time_obj):
        return (time_obj.hours * 3600 + time_obj.minutes * 60 + time_obj.seconds) * 1000 + time_obj.milliseconds
    
    def generate_dubbed_audio(self, srt_items, speaker_wav, language="ar", speed_adjust=True):
        output_segments = []
        
        for item in srt_items:
            text = item['text']
            target_duration = item['duration']
            
            if not text.strip():
                silence = AudioSegment.silent(duration=target_duration)
                output_segments.append({
                    'audio': silence,
                    'start': item['start'],
                    'end': item['end']
                })
                continue
            
            audio_path = voice_engine.clone_voice(text, speaker_wav, language)
            
            if audio_path and os.path.exists(audio_path):
                audio = AudioSegment.from_file(audio_path)
                
                if speed_adjust and len(audio) > 0:
                    current_duration = len(audio)
                    speed_ratio = current_duration / target_duration
                    speed_ratio = max(0.7, min(1.3, speed_ratio))
                    
                    if abs(speed_ratio - 1.0) > 0.05:
                        audio = self._adjust_speed(audio, speed_ratio)
                
                if len(audio) > target_duration:
                    audio = audio[:target_duration]
                elif len(audio) < target_duration:
                    padding = AudioSegment.silent(duration=target_duration - len(audio))
                    audio = audio + padding
                
                output_segments.append({
                    'audio': audio,
                    'start': item['start'],
                    'end': item['end']
                })
            else:
                silence = AudioSegment.silent(duration=target_duration)
                output_segments.append({
                    'audio': silence,
                    'start': item['start'],
                    'end': item['end']
                })
        
        return self._assemble_final_audio(output_segments)
    
    def _adjust_speed(self, audio_segment, speed_ratio):
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_in:
            audio_segment.export(temp_in.name, format='wav')
            temp_in_path = temp_in.name
        
        temp_out_path = temp_in_path.replace('.wav', '_speed.wav')
        
        try:
            subprocess.run([
                'ffmpeg', '-y', '-i', temp_in_path,
                '-filter:a', f'atempo={1/speed_ratio}',
                '-vn', temp_out_path
            ], check=True, capture_output=True)
            
            adjusted = AudioSegment.from_file(temp_out_path)
            
            os.unlink(temp_in_path)
            os.unlink(temp_out_path)
            
            return adjusted
        except:
            os.unlink(temp_in_path)
            if os.path.exists(temp_out_path):
                os.unlink(temp_out_path)
            return audio_segment
    
    def _assemble_final_audio(self, segments):
        if not segments:
            return None
        
        max_end = max(s['end'] for s in segments)
        final_audio = AudioSegment.silent(duration=max_end)
        
        for seg in segments:
            position = seg['start']
            final_audio = final_audio.overlay(seg['audio'], position=position)
        
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"dubbed_{uuid.uuid4()}.wav")
        final_audio.export(output_path, format='wav', parameters=["-ar", "44100", "-ac", "2"])
        
        return output_path

srt_processor = SRTDubbingProcessor()

# =============================================================
# Database Models
# =============================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    usage_tts = db.Column(db.Integer, default=0)
    usage_dub = db.Column(db.Integer, default=0)
    usage_srt = db.Column(db.Integer, default=0)
    
    unlocked_tts = db.Column(db.Boolean, default=False)
    unlocked_dub = db.Column(db.Boolean, default=False)
    unlocked_srt = db.Column(db.Boolean, default=False)

class DubbingJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_email = db.Column(db.String(120))
    status = db.Column(db.String(20), default='pending')
    progress = db.Column(db.Integer, default=0)
    output_audio = db.Column(db.String(255))
    target_language = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

with app.app_context():
    db.create_all()

# =============================================================
# API Routes
# =============================================================

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'tts_available': TTS_AVAILABLE,
        'model_loaded': voice_engine.model_loaded,
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/voices/upload', methods=['POST'])
def upload_voice_sample():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        file = request.files['audio']
        email = request.form.get('email', 'guest')
        language = request.form.get('language', 'ar')
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        filename = f"voice_{email}_{uuid.uuid4()}.wav"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        audio = AudioSegment.from_file(filepath)
        audio = audio.set_channels(1).set_frame_rate(24000)
        audio.export(filepath, format='wav')
        
        return jsonify({
            'success': True,
            'filename': filename,
            'duration': len(audio) / 1000,
            'message': 'Voice sample uploaded successfully'
        })
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dubbing/create', methods=['POST'])
def create_dubbing_job():
    try:
        data = request.get_json()
        
        srt_content = data.get('srt_content')
        voice_sample = data.get('voice_sample')
        target_lang = data.get('target_language', 'ar')
        email = data.get('email', 'guest')
        
        if not srt_content:
            return jsonify({'error': 'SRT content required'}), 400
        
        user = User.query.filter_by(email=email).first()
        if user and not user.unlocked_dub and user.usage_dub >= 3:
            return jsonify({'error': 'Free limit reached', 'upgrade': True}), 403
        
        srt_items = srt_processor.parse_srt(srt_content)
        if not srt_items:
            return jsonify({'error': 'Invalid SRT format'}), 400
        
        job = DubbingJob(
            user_email=email,
            target_language=target_lang,
            status='processing'
        )
        db.session.add(job)
        db.session.commit()
        
        try:
            speaker_wav = None
            if voice_sample and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], voice_sample)):
                speaker_wav = os.path.join(app.config['UPLOAD_FOLDER'], voice_sample)
            
            output_path = srt_processor.generate_dubbed_audio(srt_items, speaker_wav, target_lang)
            
            if output_path:
                job.status = 'completed'
                job.output_audio = output_path
                job.completed_at = datetime.utcnow()
                job.progress = 100
                
                if user and not user.unlocked_dub:
                    user.usage_dub += 1
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'job_id': job.job_id,
                    'status': 'completed',
                    'audio_url': f'/api/dubbing/download/{job.job_id}',
                    'duration': sum(item['duration'] for item in srt_items) / 1000
                })
            else:
                raise Exception("Audio generation failed")
                
        except Exception as process_error:
            job.status = 'failed'
            job.error_message = str(process_error)
            db.session.commit()
            raise process_error
            
    except Exception as e:
        logger.error(f"Dubbing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dubbing/status/<job_id>')
def get_job_status(job_id):
    job = DubbingJob.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'job_id': job.job_id,
        'status': job.status,
        'progress': job.progress,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'error': job.error_message
    })

@app.route('/api/dubbing/download/<job_id>')
def download_dubbing(job_id):
    job = DubbingJob.query.filter_by(job_id=job_id).first()
    if not job or job.status != 'completed':
        return jsonify({'error': 'Audio not ready'}), 404
    
    if not job.output_audio or not os.path.exists(job.output_audio):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(
        job.output_audio,
        as_attachment=True,
        download_name=f"dubbed_{job_id}.wav",
        mimetype='audio/wav'
    )

@app.route('/api/tts/clone', methods=['POST'])
def tts_clone():
    try:
        data = request.get_json()
        text = data.get('text')
        voice_sample = data.get('voice_sample')
        language = data.get('language', 'ar')
        
        if not text:
            return jsonify({'error': 'Text required'}), 400
        
        speaker_wav = None
        if voice_sample:
            potential_path = os.path.join(app.config['UPLOAD_FOLDER'], voice_sample)
            if os.path.exists(potential_path):
                speaker_wav = potential_path
        
        output_path = voice_engine.clone_voice(text, speaker_wav, language)
        
        if output_path and os.path.exists(output_path):
            with open(output_path, 'rb') as f:
                audio_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            return jsonify({
                'success': True,
                'audio_base64': audio_base64,
                'format': 'wav'
            })
        else:
            return jsonify({'error': 'Generation failed'}), 500
            
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password')
    
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email exists'}), 400
    
    user = User(
        email=email,
        password=generate_password_hash(password),
        is_verified=True
    )
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'success': True, 'email': email})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password')
    
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return jsonify({
        'success': True,
        'email': user.email,
        'unlocked': {
            'tts': user.unlocked_tts,
            'dub': user.unlocked_dub,
            'srt': user.unlocked_srt
        },
        'usage': {
            'tts': user.usage_tts,
            'dub': user.usage_dub,
            'srt': user.usage_srt
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
'''

with open('/mnt/kimi/output/server-complete.py', 'w', encoding='utf-8') as f:
    f.write(server_full)

print("✅ تم إنشاء server.py الكامل والمصحح")
