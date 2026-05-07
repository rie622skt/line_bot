import os
import google.generativeai as genai
from dotenv import load_dotenv

# .envファイルからAPIキーを読み込む
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("エラー: .env に GEMINI_API_KEY が設定されていません。")
    exit()

genai.configure(api_key=api_key)

print("--- 現在のAPIキーでテキスト生成に使えるモデル一覧 ---")
try:
    available_models = []
    for m in genai.list_models():
        # 文章を生成できる（generateContentに対応している）モデルだけを絞り込む
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
            available_models.append(m.name)
            
    if not available_models:
        print("※テキスト生成に使えるモデルが1つも見つかりませんでした。APIキーの権限や状態を確認してください。")
    else:
        print("-----------------------------------------------------")
        print("💡 上記のリストに出た名前（'models/' の後ろの部分）が、")
        print("今あなたの環境で【100%確実に動く】モデル名です。")

except Exception as e:
    print(f"APIとの通信中にエラーが発生しました: {e}")