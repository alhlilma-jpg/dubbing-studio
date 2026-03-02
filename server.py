from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from gtts import gTTS
import os
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

LANGUAGES = {
    'en': 'en',
    'es': 'es',
    'fr': 'fr',
    'de': 'de',
    'ru': 'ru',
    'tr': 'tr',
    'ar': 'ar',
    'zh': 'zh-CN',
    'hi': 'hi',
    'fa': 'fa',
    'it': 'it',
    'nl': 'nl',
    'sv': 'sv',
}

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/dub', methods=['POST'])
def dub():
    logger.info('=== DUB REQUEST STARTED ===')
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        duration = data.get('duration', 0)
        
        logger.info(f'Text: {text[:50]}...')
        logger.info(f'Language: {lang}')
        logger.info(f'Duration: {duration}ms')
        
        if not text or len(text.strip()) == 0:
            return jsonify({'error': 'No text'}), 400
        
        lang_code = LANGUAGES.get(lang, 'ar')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = f"/tmp/{filename}"
        
        logger.info(f'Generating TTS with gTTS...')
        
        # توليد الصوت
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.save(filepath)
        logger.info('TTS generation completed')
        
        # ضبط السرعة لتطابق المدة
        if duration > 0 and os.path.exists(filepath):
            try:
                from pydub import AudioSegment
                from pydub.effects import speedup
                
                sound = AudioSegment.from_mp3(filepath)
                original_duration = len(sound)
                speed_ratio = original_duration / duration
                speed_ratio = max(0.5, min(2.0, speed_ratio))
                
                logger.info(f'Original: {original_duration}ms, Target: {duration}ms, Speed: {speed_ratio}x')
                
                if speed_ratio != 1.0:
                    faster_sound = speedup(sound, speed_ratio)
                    faster_sound.export(filepath, format='mp3')
                    logger.info('Speed adjusted successfully')
                    
            except Exception as e:
                logger.error(f'Speed adjustment error: {str(e)}')
        
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f'File exists! Size: {file_size} bytes')
            
            if file_size > 0:
                logger.info(f'=== DUB SUCCESS: {filename} ===')
                return jsonify({
                    'success': True, 
                    'file': filename,
                    'size': file_size
                })
            else:
                return jsonify({'error': 'File empty'}), 500
        else:
            return jsonify({'error': 'File not created'}), 500
            
    except Exception as e:
        logger.error(f'=== DUB ERROR: {str(e)} ===')
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    try:
        filepath = f"/tmp/{filename}"
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename, mimetype='audio/mpeg')
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
