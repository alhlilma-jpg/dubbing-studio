#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sl-Dubbing & Translation — Backend
XTTS v2 Voice Cloning | Flask
"""
import os, uuid, logging, time
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS - مهم جداً للسماح لـ GitHub Pages بالاتصال
CORS(app, resources={r"/api/*": {
    "origins": [
        "https://sl-dubbing.github.io",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "*"
    ],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
db = SQLAlchemy(app)

# مجلدات الملفات
AUDIO_DIR = Path('/tmp/sl_audio')
VOICE_DIR = Path('/tmp/sl_voices')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# XTTS v2
TTS_ENGINE = None

def load_tts():
    global TTS_ENGINE
    if TTS_ENGINE is not None:
        return TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("Loading XTTS v2 model...")
        TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 loaded")
        return TTS_ENGINE
    except Exception as e:
        logger.error(f"❌ XTTS load error: {e}")
        return None

# خرائط اللغات
XTTS_LANG_MAP = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh-cn', 'hi': 'hi', 'nl': 'nl',
    'fa': None, 'sv': None,
}

GTTS_LANG_MAP = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh', 'hi': 'hi', 'fa': 'fa', 'sv': 'sv', 'nl': 'nl'
}

# نموذج المستخدم
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    voice_sample = db.Column(db.String(500))
    usage_tts = db.Column(db.Integer, default=0)
    usage_dub = db.Column(db.Integer, default=0)
    usage_srt = db.Column(db.Integer, default=0)
    unlocked_tts = db.Column(db.Boolean, default=False)
    unlocked_dub = db.Column(db.Boolean, default=False)
    unlocked_srt = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

GUEST_LIMIT = 6
GUEST_USAGE = {}

def reset_guest(ip):
    if ip not in GUEST_USAGE:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'ts': time.time()}
    elif time.time() - GUEST_USAGE[ip].get('ts', 0) > 86400:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'ts': time.time()}

def get_voice_sample(email=None):
    if email:
        user = User.query.filter_by(email=email).first()
        if user and user.voice_sample and Path(user.voice_sample).exists():
            logger.info(f"Found voice sample for {email}")
            return user.voice_sample
    samples = list(VOICE_DIR.glob('*.wav')) + list(VOICE_DIR.glob('*.mp3'))
    return str(samples[-1]) if samples else None

def synthesize_xtts(text, lang_code, voice_path, output_path):
    tts = load_tts()
    if not tts:
        return False
    try:
        xtts_lang = XTTS_LANG_MAP.get(lang_code)
        if not xtts_lang:
            return False
        tts.tts_to_file(
            text=text,
            speaker_wav=voice_path,
            language=xtts_lang,
            file_path=str(output_path)
        )
        return True
    except Exception as e:
        logger.error(f"XTTS error: {e}")
        return False

def synthesize_gtts(text, lang_code, output_path):
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANG_MAP.get(lang_code, 'en')
        gTTS(text=text, lang=gtts_lang, slow=False).save(str(output_path))
        return True
    except Exception as e:
        logger.error(f"gTTS error: {e}")
        return False

def generate_audio(text, lang_code, email=None, voice_override=None):
    output_file = AUDIO_DIR / f"{uuid.uuid4()}.wav"
    voice_path = voice_override if voice_override else get_voice_sample(email)
    
    if voice_path and XTTS_LANG_MAP.get(lang_code):
        logger.info(f"Using XTTS v2 with voice for {lang_code}")
        if synthesize_xtts(text, lang_code, voice_path, output_file):
            return str(output_file), 'xtts_v2', True
    
    logger.info(f"Using gTTS for {lang_code}")
    mp3_file = output_file.with_suffix('.mp3')
    if synthesize_gtts(text, lang_code, mp3_file):
        return str(mp3_file), 'gtts', False
    
    return None, None, False

# Endpoints
@app.route('/')
def root():
    return jsonify({'status': 'ok', 'service': 'sl-Dubbing Backend'})

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'xtts_ready': TTS_ENGINE is not None
    })

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        pw = data.get('password', '')
        
        if not email or '@' not in email:
            return jsonify({'error': 'بريد غير صحيح'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد مسجل'}), 400
        
        user = User(email=email, password=generate_password_hash(pw))
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'success': True, 'email': email}), 201
    except Exception as e:
        logger.error(f"Register error: {e}")
        return jsonify({'error': 'خطأ في التسجيل'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        pw = data.get('password', '')
        
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, pw):
            return jsonify({'error': 'بيانات غير صحيحة'}), 401
        
        return jsonify({
            'success': True,
            'email': user.email,
            'has_voice': bool(user.voice_sample)
        })
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'خطأ في الدخول'}), 500

@app.route('/api/upload-voice', methods=['POST'])
def upload_voice():
    try:
        email = request.form.get('email', '').strip().lower()
        logger.info(f"Upload voice request - Email: {email}")
        
        if 'voice' not in request.files:
            return jsonify({'error': 'لم يتم رفع ملف'}), 400
        
        file = request.files['voice']
        if not file.filename:
            return jsonify({'error': 'اسم الملف فارغ'}), 400
        
        ext = Path(file.filename).suffix.lower()
        if ext not in ['.wav', '.mp3', '.ogg', '.m4a']:
            return jsonify({'error': 'WAV/MP3/OGG/M4A فقط'}), 400
        
        filename = f"voice_{uuid.uuid4()}{ext}"
        save_path = VOICE_DIR / filename
        file.save(str(save_path))
        
        # تحويل إلى WAV
        if ext != '.wav':
            try:
                import subprocess
                wav_path = save_path.with_suffix('.wav')
                subprocess.run(
                    ['ffmpeg', '-y', '-i', str(save_path), '-ar', '22050', '-ac', '1', str(wav_path)],
                    capture_output=True, timeout=60
                )
                if wav_path.exists():
                    os.remove(str(save_path))
                    save_path = wav_path
            except Exception as e:
                logger.warning(f"FFmpeg error: {e}")
        
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                user.voice_sample = str(save_path)
                db.session.commit()
        
        logger.info(f"Voice saved: {save_path}")
        return jsonify({
            'success': True,
            'message': 'تم الحفظ بنجاح ✅',
            'voice_path': str(save_path)
        })
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': f'فشل الرفع: {str(e)}'}), 500

@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        if request.content_type and 'multipart' in request.content_type:
            text = request.form.get('text', '')
            lang = request.form.get('lang', 'ar')
            email = request.form.get('email', '').strip().lower()
            inline_voice = request.files.get('voice')
        else:
            data = request.get_json() or {}
            text = data.get('text', '')
            lang = data.get('lang', 'ar')
            email = (data.get('email') or '').strip().lower()
            inline_voice = None
        
        if not text:
            return jsonify({'error': 'النص فارغ'}), 400
        
        # حفظ العينة المرفوعة
        temp_voice_path = None
        if inline_voice and inline_voice.filename:
            ext = Path(inline_voice.filename).suffix.lower() or '.wav'
            temp_path = VOICE_DIR / f"tmp_{uuid.uuid4()}{ext}"
            inline_voice.save(str(temp_path))
            temp_voice_path = str(temp_path)
            logger.info(f"Inline voice uploaded: {temp_voice_path}")
            
            if email:
                user = User.query.filter_by(email=email).first()
                if user:
                    user.voice_sample = temp_voice_path
                    db.session.commit()
        
        # توليد الصوت
        audio_path, method, used_voice = generate_audio(
            text, lang, email, voice_override=temp_voice_path
        )
        
        # تنظيف
        if temp_voice_path:
            try:
                stored = get_voice_sample(email)
                if temp_voice_path != stored:
                    os.remove(temp_voice_path)
            except:
                pass
        
        if not audio_path or not Path(audio_path).exists():
            return jsonify({'error': 'فشل التوليد'}), 500
        
        filename = Path(audio_path).name
        audio_url = f"{request.host_url}api/download/{filename}"
        
        logger.info(f"Dub OK: {method}, used_voice={used_voice}")
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': filename,
            'method': method,
            'used_voice': used_voice
        })
    except Exception as e:
        logger.error(f"Dub error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'خطأ: {str(e)}'}), 500

@app.route('/api/download/<filename>')
def download(filename):
    try:
        filename = Path(filename).name
        filepath = AUDIO_DIR / filename
        if not filepath.exists():
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        mime = 'audio/wav' if str(filepath).endswith('.wav') else 'audio/mpeg'
        return send_file(str(filepath), as_attachment=True, download_name=filename, mimetype=mime)
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': 'فشل التنزيل'}), 500

@app.route('/api/entitlements')
def entitlements():
    try:
        email = request.args.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'غير موجود'}), 404
        
        return jsonify({
            'success': True,
            'has_voice': bool(user.voice_sample)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
