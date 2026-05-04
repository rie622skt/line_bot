import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from http import HTTPStatus
import google.generativeai as genai
from lib.supabase import SupabaseClient
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Gemini APIの初期化
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
generation_model = genai.GenerativeModel('gemini-1.5-flash')

# Supabaseクライアントの初期化
supabase = SupabaseClient()

# LINE Push APIエンドポイント
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 非同期処理用のヘルパー関数
def run_async(func, *args):
    thread = threading.Thread(target=func, args=args)
    thread.daemon = True
    thread.start()

# テキストのベクトル化
def get_embedding(text):
    # テスト環境ではダミーのベクトルを返す
    if os.getenv('ENV') == 'test' or os.getenv('GEMINI_API_KEY') == 'test_key':
        import numpy as np
        return np.random.rand(768).tolist()
    response = genai.embed_content(model='models/text-embedding-004', content=text)
    return response['embedding']

# 類似チャット履歴の検索
def search_similar_chats(line_user_id, embedding, limit=5):
    try:
        # SupabaseのRPCを呼び出して類似履歴を検索
        result = supabase.rpc('search_similar_chats', {
            'user_id': line_user_id,
            'query_embedding': embedding,
            'match_count': limit
        }).execute()
        
        return result.data
    except Exception as e:
        app.logger.error(f"Supabase search error: {str(e)}")
        return []

# チャット履歴の保存（非同期）
def store_chat_history_async(line_user_id, role, content, embedding=None):
    try:
        data = {
            'line_user_id': line_user_id,
            'role': role,
            'content': content,
            'embedding': embedding
        }
        supabase.table('chat_histories').insert(data).execute()
    except Exception as e:
        app.logger.error(f"Supabase insert error: {str(e)}")

# LINEメッセージの送信（非同期）
def send_line_message_async(line_user_id, message):
    try:
        headers = {
            'Authorization': f'Bearer {os.getenv("LINE_ACCESS_TOKEN")}',
            'Content-Type': 'application/json'
        }
        data = {
            'to': line_user_id,
            'messages': [{'type': 'text', 'text': message}]
        }
        requests.post(LINE_PUSH_URL, headers=headers, json=data)
    except Exception as e:
        app.logger.error(f"LINE push error: {str(e)}")

# システムプロンプトの生成
def generate_system_prompt(character_setting, context_messages):
    prompt = f"""【絶対命令】
あなたは以下のキャラクター設定に従い、ユーザーと対話を行ってください。AIやアシスタントとしての素振りは一切禁止します。

【キャラクター設定】
{character_setting}

【過去の関連する記憶（コンテキスト）】
"""
    for msg in context_messages:
        prompt += f"{msg['role']}: {msg['content']}\n"
    
    return prompt

@app.route('/api/worker', methods=['POST'])
def worker():
    # 環境変数チェック
    if not os.getenv('GEMINI_API_KEY'):
        return jsonify({'error': 'GEMINI_API_KEY is not set'}), 500
    try:
        data = request.get_json()
        line_user_id = data.get('line_user_id')
        text = data.get('text')
        
        if not line_user_id or not text:
            return jsonify({'error': 'Invalid payload'}), HTTPStatus.BAD_REQUEST
        
        # ユーザーメッセージのベクトル化（並列処理）
        user_embedding = get_embedding(text)
        
        # 類似チャット履歴の検索
        similar_chats = search_similar_chats(line_user_id, user_embedding)
        
        # システムプロンプトの生成
        character_setting = """
名前: サクラ
年齢: 18歳
口調のルール:
- 一人称: わたし
- 二人称: 〇〇さん（相手の名前＋さん）
- 語尾: です・ます調、時々「〜なの」「〜だよ」
性格:
- 好奇心旺盛で明るい
- 相手の話を熱心に聞く
- 趣味は読書と散歩
- 少し天然ボケ気味
"""
        system_prompt = generate_system_prompt(character_setting, similar_chats)
        
        # AI応答の生成
        full_prompt = f"{system_prompt}\n\n【直近のユーザーの発言】\n{text}"
        
        # テスト環境ではダミーの応答を返す
        if os.getenv('ENV') == 'test' or os.getenv('GEMINI_API_KEY') == 'test_key':
            ai_response = f"こんにちは！「{text}」についてお話しするの、楽しみです！"
        else:
            response = generation_model.generate_content(full_prompt)
            ai_response = response.text
        
        # 非同期処理：ユーザーメッセージとAI応答の保存
        run_async(store_chat_history_async, line_user_id, 'user', text, user_embedding)
        run_async(store_chat_history_async, line_user_id, 'model', ai_response)
        
        # 非同期処理：LINEへの応答送信
        run_async(send_line_message_async, line_user_id, ai_response)
        
        return '', HTTPStatus.OK
    
    except Exception as e:
        app.logger.error(f"Worker error: {str(e)}")
        return jsonify({'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/')
def health_check():
    return 'Worker server is running', 200

if __name__ == '__main__':
    port = int(os.getenv('WORKER_PORT', '5001'))
    app.run(port=port)