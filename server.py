from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import os
import uuid
import logging
from datetime import datetime

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

LANGUAGES = {
    'en': 'en-US-GuyNeural',
    'es': 'es-ES-ElviraNeural',
    'fr': 'fr-FR-DeniseNeural',
    'de': 'de-DE-ConradNeural',
    'ru': 'ru-RU-DmitryNeural',
    'tr': 'tr-TR-AhmetNeural',
    'ar': 'ar-SA-HamedNeural',
    'zh': 'zh-CN-XiaoxiaoNeural',
    'hi': 'hi-IN-SwaraNeural',
    'fa': 'fa-IR-FaridNeural',
    'it': 'it-IT-DiegoNeural',
    'nl': 'nl-NL-ColetteNeural',
    'sv': 'sv-SE-MattiasNeural',
}

@app.route('/api/health')
def health():
    logger.info('Health check OK')
    return jsonify({'status': 'ok'})

@app.route('/api/dub', methods=['POST'])
def dub():
    logger.info(f'=== DUB REQUEST STARTED ===')
    try:
        # التحقق من JSON
        if not request.is_json:
            logger.error('No JSON content type')
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            logger.error('Empty JSON data')
            return jsonify({'error': 'Empty JSON'}), 400
            
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        
        logger.info(f'Text length: {len(text)}')
        logger.info(f'Language: {lang}')
        logger.info(f'Text preview: {text[:100]}...')
        
        if not text or len(text.strip()) == 0:
            logger.error('Empty text provided')
            return jsonify({'error': 'No text provided'}), 400
        
        # الحصول على الصوت
        voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
        logger.info(f'Voice: {voice}')
        
        # إنشاء اسم الملف
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = f"/tmp/{filename}"
        logger.info(f'Output filepath: {filepath}')
        
        # توليد الصوت
        logger.info('Starting TTS generation...')
        try:
            communicate = edge_tts.Communicate(text, voice)
            asyncio.run(communicate.save(filepath))
            logger.info('TTS generation completed')
        except Exception as tts_error:
            logger.error(f'TTS Error: {str(tts_error)}')
            return jsonify({'error': f'TTS failed: {str(tts_error)}'}), 500
        
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
                logger.error('File exists but is EMPTY (0 bytes)')
                return jsonify({'error': 'Generated file is empty'}), 500
        else:
            logger.error('File was NOT created at all')
            return jsonify({'error': 'File not created'}), 500
            
    except Exception as e:
        logger.error(f'=== DUB ERROR: {str(e)} ===')
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    logger.info(f'Download requested: {filename}')
    try:
        filepath = f"/tmp/{filename}"
        
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f'File found: {file_size} bytes')
            
            if file_size > 0:
                return send_file(
                    filepath, 
                    as_attachment=True, 
                    download_name=filename,
                    mimetype='audio/mpeg'
                )
            else:
                logger.error('File is empty')
                return jsonify({'error': 'File is empty'}), 500
        else:
            logger.error(f'File not found: {filename}')
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        logger.error(f'Download error: {str(e)}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Server starting on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
