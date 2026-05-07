import os
import json
import hmac
import hashlib
import base64
import urllib.parse
from http import HTTPStatus
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from lib.supabase import SupabaseClient

load_dotenv()

app = Flask(__name__)

# Supabaseクライアントの初期化
supabase = SupabaseClient()

# LINE Reply APIエンドポイント
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

# LINE署名検証関数
def verify_signature(payload, signature):
    # テスト環境では常に検証成功
    if os.getenv('ENV') == 'test' or os.getenv('LINE_CHANNEL_SECRET') == 'test_secret':
        return True
        
    channel_secret = os.getenv('LINE_CHANNEL_SECRET')
    if not channel_secret:
        raise ValueError("LINE_CHANNEL_SECRET is not set")
        
    hash = hmac.new(channel_secret.encode('utf-8'), payload, hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash).decode('utf-8')
    return hmac.compare_digest(expected_signature, signature)

# LINE Reply APIでメッセージを送信
def reply_line_message(reply_token, message_text):
    try:
        headers = {
            'Authorization': f'Bearer {os.getenv("LINE_CHANNEL_ACCESS_TOKEN")}',
            'Content-Type': 'application/json'
        }
        data = {
            'replyToken': reply_token,
            'messages': [{'type': 'text', 'text': message_text}]
        }
        res = requests.post(LINE_REPLY_URL, headers=headers, json=data)
        if res.status_code != 200:
            app.logger.error(f"LINE Reply API Error: {res.text}")
    except Exception as e:
        app.logger.error(f"LINE reply error: {str(e)}")

# Postbackデータを処理
def handle_postback(event):
    try:
        reply_token = event.get('replyToken', '')
        user_id = event['source']['userId']
        postback_data = event['postback']['data']
        
        # クエリパラメータを解析 (例: action=set_persona&value=friendly)
        params = urllib.parse.parse_qs(postback_data)
        action = params.get('action', [None])[0]
        value = params.get('value', [None])[0]
        
        if not action or not value:
            app.logger.error(f"Invalid postback data: {postback_data}")
            return
        
        # upsertするデータを構築
        config_data = {'line_user_id': user_id}
        
        if action == 'set_persona':
            config_data['persona_type'] = value
            reply_text = f"性格を「{value}」に設定したよ！"
        elif action == 'set_brevity':
            config_data['brevity_level'] = value
            reply_text = f"返信の長さを「{value}」に設定したよ！"
        else:
            app.logger.error(f"Unknown action: {action}")
            return
        
        # Supabaseに upsert
        supabase.table('user_configs').upsert(config_data).execute()
        app.logger.info(f"User config updated: {config_data}")
        
        # 確認メッセージを返信
        if reply_token:
            reply_line_message(reply_token, reply_text)
    
    except Exception as e:
        app.logger.error(f"Postback handling error: {str(e)}")

@app.route('/api/webhook', methods=['POST'])
def webhook():
    try:
        # 環境変数チェック
        if not os.getenv('LINE_CHANNEL_SECRET'):
            return jsonify({'error': 'LINE_CHANNEL_SECRET is not set'}), HTTPStatus.INTERNAL_SERVER_ERROR
            
        # 署名検証
        payload = request.get_data()
        signature = request.headers.get('X-Line-Signature', '')
        if not verify_signature(payload, signature):
            return jsonify({'error': 'Invalid signature'}), HTTPStatus.UNAUTHORIZED
        
        # イベント処理
        events = request.json.get('events', [])
        for event in events:
            # Postbackイベントの処理
            if event['type'] == 'postback':
                handle_postback(event)
                continue
            
            # テキストメッセージイベントの処理
            if event['type'] == 'message' and event['message']['type'] == 'text':
                user_id = event['source']['userId']
                text = event['message']['text']
                reply_token = event.get('replyToken', '')
                
                data = {
                    'line_user_id': user_id,
                    'text': text,
                    'reply_token': reply_token
                }
                
                # テスト環境ではWorkerを直接呼び出す
                if os.getenv('ENV') == 'test' or os.getenv('LINE_CHANNEL_SECRET') == 'test_secret':
                    worker_url = "http://localhost:5001/api/worker"
                    response = requests.post(worker_url, json=data)
                    if response.status_code != 200:
                        app.logger.error(f"Direct worker error: {response.text}")
                else:

                    # QStashにタスクをキューイング
                    qstash_token = os.getenv('QSTASH_TOKEN')
                    
                    headers = {
                        'Authorization': f'Bearer {qstash_token}',
                        'Content-Type': 'application/json'
                    }
                    
                    # 環境変数を使わず、直接あなたのVercelのURLを書き込む（確実！）
                    worker_url = "https://line-bot-cwlc.vercel.app/api/worker"
                    
                    # 強制的にUS-EAST-1のサーバーを指定する
                    publish_url = f"https://qstash-us-east-1.upstash.io/v2/publish/{worker_url}"
                    
                    response = requests.post(
                        publish_url,
                        headers=headers,
                        json=data
                    )

                    if response.status_code != 200:
                        app.logger.error(f"QStash error: {response.text}")
        
        return '', HTTPStatus.OK
    
    except Exception as e:
        app.logger.error(f"Webhook error: {str(e)}")
        return jsonify({'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

if __name__ == '__main__':
    app.run(port=5000)
