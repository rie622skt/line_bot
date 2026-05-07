import os
import google.generativeai as genai
from dotenv import load_dotenv

# .envファイルからAPIキーを読み込む
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("❌ エラー: .env に GEMINI_API_KEY が見つかりません。")
    exit()

genai.configure(api_key=api_key)

# あなたが指定したモデルでテストを実行
model_name = 'gemini-2.5-flash-lite'
print(f"--- API生存確認テスト開始 ---")
print(f"テスト対象モデル: {model_name}")

try:
    model = genai.GenerativeModel(model_name)
    # APIを実際に叩く（最小限の文字数で）
    response = model.generate_content("テスト通信です。正常なら「OK」とだけ返してください。")
    
    print("\n✅ 【判定：生存】")
    print("APIは正常に機能しています！上限（Quota）には達していません。")
    print(f"AIからの応答: {response.text.strip()}")
    print("→ Vercelで動かないなら、原因は100%「Vercel側の環境変数設定ミス」です。")

except Exception as e:
    error_msg = str(e).lower()
    print("\n❌ 【判定：死亡（エラー）】")
    
    if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
        print("⚠️ 理由: APIの上限に達しているか、無料枠が制限（Limit: 0）されています。")
        print("→ このキーは今日はもう使えません。明日のリセットを待つか、別アカウントでのキー再発行が必要です。")
    elif "404" in error_msg or "not found" in error_msg:
        print("⚠️ 理由: 指定したモデルが存在しません。モデル名にタイポがあります。")
    else:
        print(f"⚠️ 理由: その他のエラーです。詳細:\n{e}")