from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import os
import uuid
import tempfile
import logging

# إعداد logging لظهور الأخطاء في Render Logs
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
    logger.info('Health check requested')
    return jsonify({'status': 'ok'})

@app.route('/api/dub', methods=['POST'])
def dub():
    logger.info('Received dub request')
    try:
        # التحقق من وجود data
        if not request.is_json:
            logger.error('No JSON data')
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        
        logger.info(f'Text: {text[:50]}... Lang: {lang}')
        
        if not text or len(text.strip()) == 0:
            logger.error('Empty text')
            return jsonify({'error': 'لا يوجد نص'}), 400
        
        voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        logger.info(f'Generating audio: {filename}')
        
        # توليد الصوت
        asyncio.run(generate_audio(text, voice, filepath))
        
        # التحقق من الملف
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f'File created: {file_size} bytes')
            
            if file_size > 0:
                return jsonify({
                    'success': True, 
                    'file': filename, 
                    'message': 'تم التوليد بنجاح',
                    'size': file_size
                })
            else:
                logger.error('File is empty')
                return jsonify({'error': 'الملف فارغ'}), 500
        else:
            logger.error('File not created')
            return jsonify({'error': 'فشل إنشاء الملف'}), 500
            
    except Exception as e:
        logger.error(f'Error: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    logger.info(f'Download requested: {filename}')
    try:
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f'File found: {file_size} bytes')
            return send_file(
                filepath, 
                as_attachment=True, 
                download_name=filename,
                mimetype='audio/mpeg'
            )
        else:
            logger.error(f'File not found: {filename}')
            return jsonify({'error': 'الملف غير موجود'}), 404
            
    except Exception as e:
        logger.error(f'Download error: {str(e)}')
        return jsonify({'error': str(e)}), 500

async def generate_audio(text, voice, output_file):
    logger.info(f'Starting TTS: {voice}')
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        logger.info(f'TTS completed: {output_file}')
    except Exception as e:
        logger.error(f'TTS error: {str(e)}')
        raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Starting server on port {port}')
    app.run(debug=False, host='0.0.0.0', port=port)
