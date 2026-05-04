import os
import requests
import hmac
import hashlib
import base64
import json
from dotenv import load_dotenv
import sys

# 環境変数が設定されていない場合の警告
if not os.getenv('LINE_CHANNEL_SECRET') or not os.getenv('GEMINI_API_KEY'):
    print("警告: 必要な環境変数が設定されていません。テストをスキップします。")
    print("テストを実行するには、.envファイルに以下の変数を設定してください:")
    print(" - LINE_CHANNEL_SECRET")
    print(" - GEMINI_API_KEY")
    sys.exit(0)

# 明示的に.envファイルをロード
load_dotenv('.env')

# 環境変数ロードを確認
print("環境変数確認:")
print(f"LINE_CHANNEL_SECRET: {os.getenv('LINE_CHANNEL_SECRET') is not None}")
print(f"GEMINI_API_KEY: {os.getenv('GEMINI_API_KEY') is not None}")

# テスト用設定
TEST_USER_ID = "test_user_123"
TEST_MESSAGE = "こんにちは、調子はどう？"
VERCEL_URL = os.getenv('VERCEL_URL', 'http://localhost:5000')

def test_webhook():
    url = f"{VERCEL_URL}/api/webhook"
    
    # テスト用ダミー署名
    headers = {
        'Content-Type': 'application/json',
        'X-Line-Signature': 'dummy_signature'
    }
    
    payload = {
        "events": [
            {
                "type": "message",
                "source": {"userId": TEST_USER_ID},
                "message": {"type": "text", "text": TEST_MESSAGE}
            }
        ]
    }
    
    print("Webhookエンドポイントテスト中...")
    response = requests.post(url, json=payload, headers=headers)
    print(f"ステータスコード: {response.status_code}")
    print(f"レスポンス: {response.text}\n")

def test_worker():
    # ワーカーはポート5001で動作
    worker_base_url = os.getenv('WORKER_BASE_URL', 'http://localhost:5001')
    url = f"{worker_base_url}/api/worker"
    
    payload = {
        "line_user_id": TEST_USER_ID,
        "text": TEST_MESSAGE
    }
    
    print("Workerエンドポイントテスト中...")
    try:
        response = requests.post(url, json=payload)
        print(f"ステータスコード: {response.status_code}")
        print(f"レスポンス: {response.text}")
    except requests.exceptions.ConnectionError:
        print("接続エラー: ワーカーサーバーが起動していません")

if __name__ == '__main__':
    print("=== エンドポイントテスト開始 ===")
    
    # サーバー起動を待つ
    print("サーバー起動を待機中...")
    import time
    time.sleep(5)
    
    test_webhook()
    test_worker()
    print("=== テスト完了 ===")