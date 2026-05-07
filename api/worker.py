# FINAL_PATCH_CONFIRMED_20260506_2145
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
generation_model = genai.GenerativeModel('gemini-2.5-flash-lite')

# Supabaseクライアントの初期化
supabase = SupabaseClient()

# LINE Reply APIエンドポイント
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

# 非同期処理用のヘルパー関数（履歴保存に使用）
def run_async(func, *args):
    thread = threading.Thread(target=func, args=args)
    thread.daemon = True
    thread.start()

# テキストのベクトル化
# テキストのベクトル化
def get_embedding(text):
    # テスト環境またはAPIキーが未設定の場合はダミーを返す
    if os.getenv('ENV') == 'test' or not os.getenv('GEMINI_API_KEY'):
        return [0.0] * 768
    
    try:
        response = genai.embed_content(
            model='models/gemini-embedding-001',
            content=text,
            task_type="retrieval_query"
        )
        return response['embedding']
    except Exception as e:
        app.logger.error(f"Embedding error (skipping): {str(e)}")
        return [0.0] * 768
    
# 直近の会話履歴を取得
# 直近の会話履歴を取得
def get_recent_chats(line_user_id, limit=6):
    try:
        result = supabase.table('chat_histories')\
            .select('role, content')\
            .eq('line_user_id', line_user_id)\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        return list(reversed(result.data))
    except Exception as e:
        app.logger.error(f"Recent chats error: {str(e)}")
        return []
    
# 類似チャット履歴の検索
def search_similar_chats(line_user_id, embedding, limit=5):
    try:
        result = supabase.rpc('search_similar_chats', {
            'user_id': line_user_id,
            'query_embedding': embedding,
            'match_count': limit
        }).execute()
        return result.data
    except Exception as e:
        app.logger.error(f"Supabase search error: {str(e)}")
        return []

# チャット履歴の保存
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

# LINEメッセージの送信（Reply API）
def send_line_message(reply_token, message):
    try:
        headers = {
            'Authorization': f'Bearer {os.getenv("LINE_CHANNEL_ACCESS_TOKEN")}',
            'Content-Type': 'application/json'
        }
        data = {
            'replyToken': reply_token,
            'messages': [{'type': 'text', 'text': message}]
        }
        res = requests.post(LINE_REPLY_URL, headers=headers, json=data)
        if res.status_code != 200:
            app.logger.error(f"LINE API Error: {res.text}")
    except Exception as e:
        app.logger.error(f"LINE reply error: {str(e)}")

# システムプロンプトの生成
def generate_system_prompt(character_setting, similar_chats, recent_chats):
    prompt = f"""【絶対命令】
あなたは以下のキャラクター設定に従い、ユーザーと対話を行ってください。AIやアシスタントとしての素振りは一切禁止します。

【キャラクター設定】
{character_setting}

【過去の関連する記憶（類似検索による関連会話）】
"""
    for msg in similar_chats:
        prompt += f"{msg['role']}: {msg['content']}\n"
    
    prompt += "\n【ここまでの会話の流れ（直近の履歴）】\n"
    for msg in recent_chats:
        prompt += f"{msg['role']}: {msg['content']}\n"
    
    return prompt

@app.route('/api/worker', methods=['POST'])
def worker():
    print("--- NEW SYSTEM ACTIVATED ---")
    if not os.getenv('GEMINI_API_KEY'):
        return jsonify({'error': 'GEMINI_API_KEY is not set'}), 500
    try:
        data = request.get_json()
        line_user_id = data.get('line_user_id')
        text = data.get('text')
        reply_token = data.get('reply_token', '')
        
        if not line_user_id or not text:
            return jsonify({'error': 'Invalid payload'}), HTTPStatus.BAD_REQUEST
        
        # ユーザーメッセージのベクトル化
        user_embedding = get_embedding(text)
        
        # 類似チャット履歴の検索
        similar_chats = search_similar_chats(line_user_id, user_embedding)
        
        # 直近の会話履歴を取得
        recent_chats = get_recent_chats(line_user_id)
        
        # キャラクター設定
        character_setting = """
名前: サクラ
性格: 好奇心旺盛で明るい、読書と散歩が趣味。
口調: わたし、〇〇さん、です・ます調（時々「〜だよ」）。
"""
        system_prompt = generate_system_prompt(character_setting, similar_chats, recent_chats)
        
        # AI応答の生成（自然なチャット形式）
        full_prompt = f"{system_prompt}\n\n【直近のユーザーの発言】\nuser: {text}\nmodel: "
        
        if os.getenv('ENV') == 'test':
            ai_response = f"テスト応答: {text}"
        else:
            try:
                response = generation_model.generate_content(full_prompt)
                ai_response = response.text.strip().replace('```', '')
            except Exception as e:
                app.logger.error(f"Gemini generation error: {str(e)}")
                ai_response = f"ごめんなさい、応答の生成中にエラーが発生しました。"
        
        # 保存は非同期で実行
        run_async(store_chat_history_async, line_user_id, 'user', text, user_embedding)
        run_async(store_chat_history_async, line_user_id, 'model', ai_response)
        
        # LINE送信は同期処理で実行（Vercelの強制終了を防ぐ）
        if reply_token:
            send_line_message(reply_token, ai_response)
        else:
            app.logger.error("No reply_token available, cannot send reply")
        
        return '', HTTPStatus.OK
    
    except Exception as e:
        app.logger.error(f"Worker error: {str(e)}")
        return jsonify({'error': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/')
def health_check():
    return 'Worker server is running', 200

if __name__ == '__main__':
    app.run(port=5001)