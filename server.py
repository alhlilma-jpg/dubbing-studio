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
from functools import wraps

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'https://sl-dubbing.github.io,http://localhost:3000').split(',')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///dubbing.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['OUTPUT_FOLDER'] = '/tmp/outputs'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())

# Email config (بدون قيم افتراضية)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'

# CORS آمن
CORS(app, resources={
    r"/api/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

db = SQLAlchemy(app)
mail = Mail(app)

# Create directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# =============================================================
# Voice Cloning Engine (XTTS v2)
# =============================================================
class VoiceCloningEngine:
    def __init__(self):
        self.tts_model = None
        self.model_loaded = False
        self.load_model()

    def load_model(self):
        try:
            from TTS.api import TTS
            logger.info("Loading XTTS v2 model...")
            self.tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            self.model_loaded = True
            logger.info("✅ XTTS v2 model loaded successfully")
        except ImportError:
            logger.warning("⚠️ TTS library not installed, using fallback")
        except Exception as e:
            logger.error(f"❌ Failed to load TTS model: {e}")

    def clone_voice(self, text, speaker_wav_path, language="ar", output_path=None):
        """توليد صوت بنفس نبرة المتحدث"""
        if not self.model_loaded:
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
        """TTS احتياطي باستخدام gTTS"""
        try:
            from gtts import gTTS
            if output_path is None:
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"fallback_{uuid.uuid4()}.mp3")

            lang_map = {'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr', 'de': 'de', 
                       'it': 'it', 'ru': 'ru', 'tr': 'tr', 'zh': 'zh-cn', 'hi': 'hi'}

            tts = gTTS(text=text[:500], lang=lang_map.get(language[:2], 'en'), slow=False)
            tts.save(output_path)
            return output_path
        except Exception as e:
            logger.error(f"Fallback TTS error: {e}")
            return None

# Initialize engine
voice_engine = VoiceCloningEngine()

# =============================================================
# Audio Processing with pydub
# =============================================================
class AudioProcessor:
    def __init__(self):
        self.sample_rate = 24000

    def convert_to_wav(self, input_path, output_path=None):
        """تحويل أي صوت لـ WAV mono 24kHz"""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(input_path)
            audio = audio.set_channels(1).set_frame_rate(24000)

            if output_path is None:
                output_path = input_path.rsplit('.', 1)[0] + '.wav'

            audio.export(output_path, format='wav')
            return output_path
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return None

    def adjust_speed(self, audio_segment, speed_ratio):
        """تعديل سرعة الصوت"""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_in:
                audio_segment.export(temp_in.name, format='wav')
                temp_in_path = temp_in.name

            temp_out_path = temp_in_path.replace('.wav', '_speed.wav')

            subprocess.run([
                'ffmpeg', '-y', '-i', temp_in_path,
                '-filter:a', f'atempo={max(0.5, min(2.0, 1/speed_ratio))}',
                '-vn', temp_out_path
            ], check=True, capture_output=True)

            from pydub import AudioSegment
            adjusted = AudioSegment.from_file(temp_out_path)

            os.unlink(temp_in_path)
            os.unlink(temp_out_path)

            return adjusted
        except:
            return audio_segment

    def detect_speech_segments(self, audio_path):
        """اكتشاف أجزاء الكلام"""
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            audio = AudioSegment.from_file(audio_path)
            segments = detect_nonsilent(audio, min_silence_len=500, silence_thresh=-40)
            return segments
        except:
            return []

audio_processor = AudioProcessor()

# =============================================================
# SRT Processor with Time Sync
# =============================================================
class SRTProcessor:
    def __init__(self):
        pass

    def parse_srt(self, srt_content):
        """تحليل ملف SRT"""
        try:
            import pysrt
            import tempfile

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
                    'text': sub.text.replace('\n', ' ').strip()
                })
            return items
        except Exception as e:
            logger.error(f"SRT parse error: {e}")
            # محاولة تحليل يدوي
            return self._parse_srt_manual(srt_content)

    def _time_to_ms(self, time_obj):
        return (time_obj.hours * 3600 + time_obj.minutes * 60 + time_obj.seconds) * 1000 + time_obj.milliseconds

    def _parse_srt_manual(self, content):
        """تحليل يدوي للـ SRT"""
        items = []
        pattern = r'(\d+)\s*
(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*
((?:.|
)*?)(?=
\d+\s*
|\Z)'
        matches = re.findall(pattern, content, re.MULTILINE)

        for match in matches:
            idx, start, end, text = match
            start_ms = self._parse_time(start)
            end_ms = self._parse_time(end)
            items.append({
                'index': int(idx),
                'start': start_ms,
                'end': end_ms,
                'duration': end_ms - start_ms,
                'text': text.strip().replace('\n', ' ')
            })
        return items

    def _parse_time(self, time_str):
        """تحويل وقت SRT لمللي ثانية"""
        h, m, s = time_str.split(':')
        s, ms = s.split(',')
        return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

    def generate_dubbed_audio(self, srt_items, speaker_wav, language="ar", speed_adjust=True):
        """توليد الدبلجة مع تزامن زمني"""
        from pydub import AudioSegment

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

            # توليد الصوت
            audio_path = voice_engine.clone_voice(text, speaker_wav, language)

            if audio_path and os.path.exists(audio_path):
                audio = AudioSegment.from_file(audio_path)

                # تعديل السرعة إذا لزم الأمر
                if speed_adjust and len(audio) > 0:
                    current_duration = len(audio)
                    if current_duration > 0:
                        speed_ratio = current_duration / target_duration
                        speed_ratio = max(0.7, min(1.3, speed_ratio))

                        if abs(speed_ratio - 1.0) > 0.05:
                            audio = audio_processor.adjust_speed(audio, speed_ratio)

                # ضبط الطول
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

    def _assemble_final_audio(self, segments):
        """تجميع المقاطع الصوتية"""
        from pydub import AudioSegment

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

srt_processor = SRTProcessor()

# =============================================================
# Database Models
# =============================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Usage counters
    usage_tts = db.Column(db.Integer, default=0)
    usage_dub = db.Column(db.Integer, default=0)
    usage_srt = db.Column(db.Integer, default=0)

    # Unlocked features
    unlocked_tts = db.Column(db.Boolean, default=False)
    unlocked_dub = db.Column(db.Boolean, default=False)
    unlocked_srt = db.Column(db.Boolean, default=False)

class DubbingJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()), index=True)
    user_email = db.Column(db.String(120), index=True)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    progress = db.Column(db.Integer, default=0)
    output_audio = db.Column(db.String(255))
    target_language = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

class VoiceSample(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True)
    user_email = db.Column(db.String(120))
    duration = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# =============================================================
# Authentication Decorator
# =============================================================
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authentication required'}), 401
        # يمكن إضافة JWT verification هنا
        return f(*args, **kwargs)
    return decorated_function

# =============================================================
# API Routes
# =============================================================

@app.route('/')
def index():
    return jsonify({
        'service': 'sl-Dubbing AI Server',
        'version': '2.0',
        'features': ['voice_cloning', 'srt_dubbing', 'tts'],
        'endpoints': {
            'health': '/api/health',
            'upload_voice': '/api/voices/upload',
            'create_dubbing': '/api/dubbing/create',
            'job_status': '/api/dubbing/status/<job_id>',
            'download': '/api/dubbing/download/<job_id>',
            'tts': '/api/tts/clone',
            'login': '/api/login',
            'register': '/api/register'
        }
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'tts_available': voice_engine.model_loaded,
        'timestamp': datetime.utcnow().isoformat(),
        'version': '2.0'
    })

@app.route('/api/voices/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_voice_sample():
    """رفع عينة صوتية للاستنساخ"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        file = request.files['audio']
        email = request.form.get('email', 'guest')
        language = request.form.get('language', 'ar')

        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        # التحقق من الامتداد
        allowed_extensions = {'wav', 'mp3', 'ogg', 'm4a', 'webm'}
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({'error': f'Invalid format. Allowed: {allowed_extensions}'}), 400

        # حفظ الملف
        filename = f"voice_{email.replace('@', '_')}_{uuid.uuid4()}.wav"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # تحويل لـ WAV
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{uuid.uuid4()}.{ext}")
        file.save(temp_path)

        # تحويل للمواصفات المطلوبة
        result = audio_processor.convert_to_wav(temp_path, filepath)
        os.remove(temp_path)

        if not result:
            return jsonify({'error': 'Audio conversion failed'}), 500

        # حساب المدة
        from pydub import AudioSegment
        audio = AudioSegment.from_file(filepath)
        duration = len(audio) / 1000

        # حفظ في قاعدة البيانات
        voice_sample = VoiceSample(
            filename=filename,
            user_email=email,
            duration=duration
        )
        db.session.add(voice_sample)
        db.session.commit()

        logger.info(f"Voice sample uploaded: {filename} ({duration}s)")

        return jsonify({
            'success': True,
            'filename': filename,
            'duration': duration,
            'message': 'Voice sample uploaded successfully'
        })

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dubbing/create', methods=['POST'])
@limiter.limit("5 per minute")
def create_dubbing_job():
    """إنشاء مهمة دبلجة جديدة"""
    try:
        data = request.get_json()

        srt_content = data.get('srt_content')
        voice_sample = data.get('voice_sample')
        target_lang = data.get('target_language', 'ar')
        email = data.get('email', 'guest')
        speed_adjust = data.get('speed_adjust', True)

        if not srt_content:
            return jsonify({'error': 'SRT content required'}), 400

        # التحقق من الحدود
        user = User.query.filter_by(email=email).first()
        if user and not user.unlocked_dub and user.usage_dub >= 3:
            return jsonify({
                'error': 'Free limit reached',
                'upgrade_url': '/#payment',
                'upgrade': True
            }), 403

        # تحليل SRT
        srt_items = srt_processor.parse_srt(srt_content)
        if not srt_items:
            return jsonify({'error': 'Invalid SRT format'}), 400

        if len(srt_items) > 100:
            return jsonify({'error': 'Too many subtitles (max 100)'}), 400

        # إنشاء المهمة
        job = DubbingJob(
            user_email=email,
            target_language=target_lang,
            status='processing',
            progress=10
        )
        db.session.add(job)
        db.session.commit()

        # معالجة الصوت
        try:
            speaker_wav = None
            if voice_sample:
                potential_path = os.path.join(app.config['UPLOAD_FOLDER'], voice_sample)
                if os.path.exists(potential_path):
                    speaker_wav = potential_path

            job.progress = 30
            db.session.commit()

            # توليد الدبلجة
            output_path = srt_processor.generate_dubbed_audio(
                srt_items, speaker_wav, target_lang, speed_adjust
            )

            job.progress = 90
            db.session.commit()

            if output_path:
                job.status = 'completed'
                job.output_audio = output_path
                job.completed_at = datetime.utcnow()
                job.progress = 100

                if user and not user.unlocked_dub:
                    user.usage_dub += 1

                db.session.commit()

                total_duration = sum(item['duration'] for item in srt_items) / 1000

                return jsonify({
                    'success': True,
                    'job_id': job.job_id,
                    'status': 'completed',
                    'audio_url': f'/api/dubbing/download/{job.job_id}',
                    'duration': total_duration,
                    'segments': len(srt_items)
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
@limiter.limit("30 per minute")
def get_job_status(job_id):
    """الحصول على حالة المهمة"""
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
@limiter.limit("10 per minute")
def download_dubbing(job_id):
    """تحميل الملف الصوتي"""
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
@limiter.limit("10 per minute")
def tts_clone():
    """توليد صوت بنفس النبرة"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        voice_sample = data.get('voice_sample')
        language = data.get('language', 'ar')

        if not text:
            return jsonify({'error': 'Text required'}), 400

        if len(text) > 1000:
            return jsonify({'error': 'Text too long (max 1000 chars)'}), 400

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
                'format': 'wav',
                'duration': len(audio_base64) * 0.75 / 1000  # تقدير تقريبي
            })
        else:
            return jsonify({'error': 'Generation failed'}), 500

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    """تسجيل مستخدم جديد"""
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')

    if not email or '@' not in email:
        return jsonify({'error': 'Invalid email'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be 8+ characters'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    user = User(
        email=email,
        password=generate_password_hash(password, method='pbkdf2:sha256'),
        is_verified=True  # يمكن تفعيل OTP لاحقاً
    )
    db.session.add(user)
    db.session.commit()

    logger.info(f"New user registered: {email}")

    return jsonify({
        'success': True,
        'email': email,
        'message': 'Registration successful'
    })

@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """تسجيل الدخول"""
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Invalid credentials'}), 401

    if not user.is_verified:
        return jsonify({'error': 'Account not verified'}), 403

    user.last_login = datetime.utcnow()
    db.session.commit()

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

@app.route('/api/user/usage', methods=['GET'])
def get_usage():
    """الحصول على استهلاك المستخدم"""
    email = request.args.get('email', '').lower()
    if not email:
        return jsonify({'error': 'Email required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'email': user.email,
        'usage': {
            'tts': user.usage_tts,
            'dub': user.usage_dub,
            'srt': user.usage_srt
        },
        'limits': {
            'tts': 'unlimited' if user.unlocked_tts else 6,
            'dub': 'unlimited' if user.unlocked_dub else 3,
            'srt': 'unlimited' if user.unlocked_srt else 6
        },
        'unlocked': {
            'tts': user.unlocked_tts,
            'dub': user.unlocked_dub,
            'srt': user.unlocked_srt
        }
    })

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded', 'retry_after': e.description}), 429

@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

# =============================================================
# Run Server
# =============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
