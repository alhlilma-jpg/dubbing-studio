from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import os
import uuid
import logging
import random
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ✅ أصوات رجالية فقط (Male Voices)
LANGUAGES = {
    'en': 'en-US-ChristopherNeural',      # Male
    'es': 'es-ES-AlvaroNeural',           # Male
    'fr': 'fr-FR-HenriNeural',            # Male
    'de': 'de-DE-ConradNeural',           # Male
    'ru': 'ru-RU-DmitryNeural',           # Male
    'tr': 'tr-TR-AhmetNeural',            # Male
    'ar': 'ar-SA-HamedNeural',            # Male
    'zh': 'zh-CN-YunxiNeural',            # Male
    'hi': 'hi-IN-MadhurNeural',           # Male
    'fa': 'fa-IR-FaridNeural',            # Male
    'it': 'it-IT-DiegoNeural',            # Male
    'nl': 'nl-NL-MaartenNeural',          # Male
    'sv': 'sv-SE-MattiasNeural',          # Male
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
        
        voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = f"/tmp/{filename}"
        
        logger.info(f'Voice: {voice}')
        logger.info('Starting TTS generation...')
        
        # ✅ محاولة متعددة في حالة فشل الاتصال
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f'Attempt {attempt + 1}/{max_retries}')
                
                communicate = edge_tts.Communicate(text, voice)
                asyncio.run(communicate.save(filepath))
                
                logger.info('TTS generation completed')
                break
                
            except Exception as tts_error:
                logger.error(f'Attempt {attempt + 1} failed: {str(tts_error)}')
                if attempt < max_retries - 1:
                    time.sleep(2)  # انتظر قبل المحاولة التالية
                else:
                    return jsonify({'error': f'TTS failed: {str(tts_error)}'}), 500
        
        # ✅ ضبط السرعة لتطابق المدة
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
        
        # التحقق من الملف
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
