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
def send_line_message(reply_token, messages):
    try:
        headers = {
            'Authorization': f'Bearer {os.getenv("LINE_CHANNEL_ACCESS_TOKEN")}',
            'Content-Type': 'application/json'
        }
        # 文字列の場合はテキストメッセージに変換、リストの場合はそのまま使用
        if isinstance(messages, str):
            messages = [{'type': 'text', 'text': messages}]
        data = {
            'replyToken': reply_token,
            'messages': messages
        }
        res = requests.post(LINE_REPLY_URL, headers=headers, json=data)
        if res.status_code != 200:
            app.logger.error(f"LINE API Error: {res.text}")
    except Exception as e:
        app.logger.error(f"LINE reply error: {str(e)}")

# 設定パネル（カルーセル）の生成
def build_settings_carousel():
    return [
        {
            'type': 'template',
            'altText': '設定メニュー',
            'template': {
                'type': 'carousel',
                'columns': [
                    {
                        'title': '性格を選ぶ',
                        'text': '好きな性格を選んでね',
                        'actions': [
                            {
                                'type': 'postback',
                                'label': 'フレンドリー',
                                'data': 'action=set_persona&value=friendly',
                                'displayText': '性格: フレンドリー'
                            },
                            {
                                'type': 'postback',
                                'label': 'クール',
                                'data': 'action=set_persona&value=cool',
                                'displayText': '性格: クール'
                            },
                            {
                                'type': 'postback',
                                'label': 'ツンデレ',
                                'data': 'action=set_persona&value=tsundere',
                                'displayText': '性格: ツンデレ'
                            }
                        ]
                    },
                    {
                        'title': '会話の長さ',
                        'text': '返信の長さを選んでね',
                        'actions': [
                            {
                                'type': 'postback',
                                'label': '短め',
                                'data': 'action=set_brevity&value=short',
                                'displayText': '長さ: 短め'
                            },
                            {
                                'type': 'postback',
                                'label': '普通',
                                'data': 'action=set_brevity&value=normal',
                                'displayText': '長さ: 普通'
                            },
                            {
                                'type': 'postback',
                                'label': '長め',
                                'data': 'action=set_brevity&value=long',
                                'displayText': '長さ: 長め'
                            }
                        ]
                    }
                ]
            }
        }
    ]

# ユーザー設定の取得
def get_user_config(line_user_id):
    """Supabaseの user_configs テーブルからユーザー設定を取得する"""
    try:
        result = supabase.table('user_configs')\
            .select('*')\
            .eq('line_user_id', line_user_id)\
            .execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
    except Exception as e:
        app.logger.error(f"get_user_config error: {str(e)}")
    # デフォルト設定を返す
    return {
        'persona_type': 'friendly',
        'brevity_level': 'short'
    }

# システムプロンプトの生成
def generate_system_prompt(character_setting, similar_chats, recent_chats, user_config=None):
    if user_config is None:
        user_config = {'persona_type': 'friendly', 'brevity_level': 'short'}
    
    persona_type = user_config.get('persona_type', 'friendly')
    brevity_level = user_config.get('brevity_level', 'short')
    
    # 性格タイプに応じた指示
    persona_instructions = {
        'friendly': '親しみやすく、温かい態度で接してください。フレンドリーで優しい口調を心がけてください。',
        'cool': 'クールで落ち着いた態度で接してください。あまり感情を表に出さず、知的でスマートな印象を与えてください。',
        'tsundere': 'ツンデレな態度で接してください。最初は少し素っ気ないけど、実は気にかけているような、照れ屋で不器用な優しさを見せてください。'
    }
    
    # 返信の長さに応じた指示
    brevity_instructions = {
        'short': '返信は簡潔に、1〜2文程度で收めてください。',
        'normal': '返信は適度な長さで、3〜5文程度を目安にしてください。',
        'long': '返信は詳しめに、十分な説明や感情表現を含めて、6文以上で丁寧に返してください。'
    }
    
    persona_line = persona_instructions.get(persona_type, persona_instructions['friendly'])
    brevity_line = brevity_instructions.get(brevity_level, brevity_instructions['short'])
    
    prompt = f"""【絶対命令】
あなたは以下のキャラクター設定に従い、ユーザーと対話を行ってください。AIやアシスタントとしての素振りは一切禁止します。

【キャラクター設定】
{character_setting}

【性格設定】
{persona_line}

【返信の長さ】
{brevity_line}

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
        
        # 「設定」メッセージの場合 → カルーセルパネルを返して終了
        if text.strip() == '設定':
            carousel = build_settings_carousel()
            if reply_token:
                send_line_message(reply_token, carousel)
            return '', HTTPStatus.OK
        
        # ユーザーメッセージのベクトル化
        user_embedding = get_embedding(text)
        
        # 類似チャット履歴の検索
        similar_chats = search_similar_chats(line_user_id, user_embedding)
        
        # 直近の会話履歴を取得
        recent_chats = get_recent_chats(line_user_id)
        
        # ユーザー設定を取得
        user_config = get_user_config(line_user_id)
        
        # キャラクター設定
        character_setting = """
名前: サクラ
性格: 好奇心旺盛で明るい、読書と散歩が趣味。
口調: わたし、〇〇さん、です・ます調（時々「〜だよ」）。
"""
        system_prompt = generate_system_prompt(character_setting, similar_chats, recent_chats, user_config)
        
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
