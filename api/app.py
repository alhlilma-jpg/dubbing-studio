# =============================================================
# sl-Dubbing Backend — Koyeb Free Hosting
# =============================================================
import os, uuid, time, logging
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# HF Spaces: /data يبقى محفوظاً، /tmp يُمسح
# نحاول /data أولاً وإلا نستخدم مجلد محلي
_base = Path('/data') if Path('/data').exists() else Path('/app')
AUDIO_DIR = _base / 'sl_audio'
VOICE_DIR  = _base / 'sl_voices'
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Storage: AUDIO={AUDIO_DIR} VOICE={VOICE_DIR}")

# ── XTTS v2 ──────────────────────────────────────────────────
TTS_ENGINE = None

def load_tts():
    global TTS_ENGINE
    if TTS_ENGINE is not None:
        return TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("Loading XTTS v2...")
        TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 ready")
        return TTS_ENGINE
    except Exception as e:
        logger.error(f"XTTS load error: {e}")
        return None

XTTS_LANGS = {
    'ar':'ar','en':'en','es':'es','fr':'fr','de':'de',
    'it':'it','ru':'ru','tr':'tr','zh':'zh-cn','hi':'hi','nl':'nl'
}
GTTS_LANGS = {
    'ar':'ar','en':'en','es':'es','fr':'fr','de':'de','it':'it',
    'ru':'ru','tr':'tr','zh':'zh-TW','hi':'hi','fa':'fa','sv':'sv','nl':'nl'
}

GUEST_LIMIT = 6
GUEST_USAGE = {}

def reset_guest(ip):
    if ip not in GUEST_USAGE or time.time()-GUEST_USAGE[ip].get('ts',0) > 86400:
        GUEST_USAGE[ip] = {'tts':0,'dub':0,'srt':0,'ts':time.time()}

def get_voice(email=None):
    if email:
        p = VOICE_DIR / f"{email.replace('@','_').replace('.','_')}.wav"
        if p.exists(): return str(p)
    samples = list(VOICE_DIR.glob('*.wav'))
    return str(samples[-1]) if samples else None

def synth_xtts(text, lang, voice_path, out):
    tts = load_tts()
    if not tts: return False
    xtts_lang = XTTS_LANGS.get(lang)
    if not xtts_lang: return False
    try:
        tts.tts_to_file(text=text, speaker_wav=voice_path,
                        language=xtts_lang, file_path=str(out))
        return True
    except Exception as e:
        logger.error(f"XTTS: {e}"); return False

def synth_gtts(text, lang, out):
    try:
        from gtts import gTTS
        gTTS(text=text, lang=GTTS_LANGS.get(lang,'en')).save(str(out))
        return True
    except Exception as e:
        logger.error(f"gTTS: {e}"); return False

def generate(text, lang, email=None):
    voice = get_voice(email)
    logger.info(f"generate: lang={lang} email={email} voice={voice}")
    out   = AUDIO_DIR / f"{uuid.uuid4()}.wav"
    if voice:
        logger.info(f"Trying XTTS v2 with voice: {voice}")
        if synth_xtts(text, lang, voice, out):
            logger.info("✅ XTTS v2 success")
            return str(out), 'xtts_v2'
        logger.warning("XTTS failed → fallback gTTS")
    else:
        logger.warning(f"No voice sample found for email={email} → using gTTS")
    mp3 = out.with_suffix('.mp3')
    if synth_gtts(text, lang, mp3):
        return str(mp3), 'gtts'
    return None, None

# ══════════════════════════════════════════════════════════════
@app.route('/')
@app.route('/api/health')
def health():
    voices = list(VOICE_DIR.glob('*'))
    return jsonify({
        'status': 'ok',
        'service': 'sl-Dubbing on HF Spaces',
        'xtts_ready': TTS_ENGINE is not None,
        'voices_saved': len(voices),
        'voice_files': [v.name for v in voices]
    })

@app.route('/api/debug')
def debug():
    """endpoint للتشخيص — يظهر ملفات الصوت المحفوظة"""
    voices = list(VOICE_DIR.glob('*'))
    audios = list(AUDIO_DIR.glob('*'))
    return jsonify({
        'voice_dir': str(VOICE_DIR),
        'voice_files': [{'name': v.name, 'size': v.stat().st_size} for v in voices],
        'audio_files': len(audios),
        'xtts_loaded': TTS_ENGINE is not None
    })

@app.route('/api/upload-voice', methods=['POST'])
def upload_voice():
    try:
        email = request.form.get('email','').strip().lower()
        if 'voice' not in request.files:
            return jsonify({'error':'لم يتم رفع ملف'}), 400
        file = request.files['voice']
        ext  = Path(file.filename).suffix.lower() or '.wav'
        name = email.replace('@','_').replace('.','_') if email else f"guest_{uuid.uuid4()}"
        raw  = VOICE_DIR / f"{name}{ext}"
        file.save(str(raw))
        if ext != '.wav':
            try:
                import subprocess
                wav = VOICE_DIR / f"{name}.wav"
                subprocess.run(['ffmpeg','-y','-i',str(raw),'-ar','22050','-ac','1',str(wav)],
                               capture_output=True, timeout=30)
                if wav.exists(): raw.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"ffmpeg: {e}")
        return jsonify({'success':True,'message':'تم رفع عينة الصوت ✅'})
    except Exception as e:
        return jsonify({'error':str(e)}), 500

@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        is_form = request.content_type and 'multipart' in request.content_type
        if is_form:
            text    = request.form.get('text','')
            lang    = request.form.get('lang','ar')
            email   = request.form.get('email','').strip().lower()
            feature = request.form.get('feature','dub')
            voice_f = request.files.get('voice')
        else:
            d       = request.get_json() or {}
            text    = d.get('text','')
            lang    = d.get('lang','ar')
            email   = (d.get('email') or '').strip().lower()
            feature = d.get('feature','dub')
            voice_f = None

        if not text:
            return jsonify({'error':'النص فارغ'}), 400

        ip = request.remote_addr
        reset_guest(ip)
        if GUEST_USAGE[ip].get(feature,0) >= GUEST_LIMIT:
            return jsonify({'error':'انتهى الحد المجاني','limit_reached':True}), 403
        GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature,0) + 1
        remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]

        # حفظ العينة المرفوعة مع الطلب
        if voice_f and voice_f.filename:
            ext  = Path(voice_f.filename).suffix.lower() or '.wav'
            name = email.replace('@','_').replace('.','_') if email else f"tmp_{uuid.uuid4()}"
            vp   = VOICE_DIR / f"{name}{ext}"
            voice_f.save(str(vp))
            if ext != '.wav':
                try:
                    import subprocess
                    wav = VOICE_DIR / f"{name}.wav"
                    subprocess.run(['ffmpeg','-y','-i',str(vp),'-ar','22050','-ac','1',str(wav)],
                                   capture_output=True, timeout=30)
                    if wav.exists(): vp.unlink(missing_ok=True)
                except: pass

        audio_path, method = generate(text, lang, email)
        if not audio_path:
            return jsonify({'error':'فشل توليد الصوت'}), 500

        fname     = Path(audio_path).name
        audio_url = f"{request.host_url.rstrip('/')}/api/download/{fname}"

        return jsonify({'success':True,'remaining':remaining,
                        'audio_url':audio_url,'method':method,'lang':lang})
    except Exception as e:
        logger.error(f"dub: {e}")
        return jsonify({'error':str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    filename = Path(filename).name
    for d in [AUDIO_DIR, VOICE_DIR]:
        p = d / filename
        if p.exists():
            mime = 'audio/wav' if filename.endswith('.wav') else 'audio/mpeg'
            return send_file(str(p), as_attachment=True, download_name=filename, mimetype=mime)
    return jsonify({'error':'الملف غير موجود'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
