# システム仕様書 — LINE AIチャットボット

> 作成日: 2026-05-06
> 対象プロジェクト: `c:/Users/riE62/python/deepseek`

---

## 1. プロジェクト概要

### 目的
LINE Messaging API 上で動作する「疑似人格AIチャットボット」を提供する。ユーザーがLINEでメッセージを送信すると、Gemini API がキャラクター性を持った返答を生成し、過去の会話履歴をベクトル類似検索でコンテキストとして利用する。

### 主要ユースケース
1. **ユーザーがLINEでメッセージを送信** → Webhookが受信
2. **QStashによる非同期処理** → Vercelの10秒タイムアウトを回避
3. **会話履歴のベクトル検索** → 類似会話をSupabase（pgvector）またはSQLiteから検索
4. **AI応答生成** → Gemini API でキャラクター性を持った応答を生成
5. **LINE Reply APIで返信** → ユーザーに応答を返す（Push APIからの移行済み）
6. **会話履歴の保存** → ユーザー発言とAI応答をDBに保存

---

## 2. システムアーキテクチャと技術スタック

### 技術スタック

| カテゴリ | 技術 | バージョン |
|---------|------|-----------|
| フレームワーク | Flask | 3.0.3 |
| ランタイム | Python | 3.14.0 |
| インフラ | Vercel (Serverless Functions) | - |
| 非同期キュー | Upstash QStash | - |
| データベース | Supabase (PostgreSQL + pgvector) / SQLite (ローカル) | - |
| AI | Google Gemini API | google-generativeai 0.8.3 |
| LINE | LINE Messaging API | - |
| ライブラリ | requests | 2.32.3 |
| ライブラリ | python-dotenv | 1.0.1 |
| ライブラリ | supabase-py | 2.11.0 |
| ライブラリ | httpx | 0.27.2 |
| ライブラリ | numpy | - |

### データの流れ

```
LINE User
  │
  │ POST (Webhook Event + replyToken)
  ▼
Vercel Webhook (api/webhook.py) ← ポート5000（ローカル）
  │
  ├── [テスト環境] ──→ POST http://localhost:5001/api/worker
  │
  └── [本番環境] ──→ Upstash QStash
                        │
                        │ 非同期キューイング
                        ▼
                    Vercel Worker (api/worker.py) ← ポート5001（ローカル）
                      │
                      ├── ① Gemini API: embed_content() → ベクトル化
                      ├── ② Supabase/SQLite: 類似会話検索 (pgvector)
                      ├── ③ Gemini API: generate_content() → 応答生成
                      ├── ④ Supabase/SQLite: 会話履歴保存
                      └── ⑤ LINE Reply API: ユーザーに返信
```

---

## 3. ディレクトリ構造と主要ファイルの役割

```
deepseek/
├── api/
│   ├── webhook.py          # LINE Webhook受信エンドポイント
│   │                       # - 署名検証（テスト時は常にパス）
│   │                       # - replyToken抽出
│   │                       # - テスト時: Worker直接呼び出し
│   │                       # - 本番時: QStash経由で非同期転送
│   │                       # - 待受ポート: 5000
│   │
│   └── worker.py           # AI推論・DB操作エンドポイント
│                           # - Gemini API: テキスト埋め込み + 応答生成
│                           # - Supabase/SQLite: 類似検索 + 保存
│                           # - LINE Reply API: ユーザー返信
│                           # - 待受ポート: 5001
│
├── lib/
│   ├── supabase.py         # Supabaseクライアント（+ SQLiteモック）
│   │                       # - テスト時: SQLite (chat_histories.db)
│   │                       # - 本番時: Supabase (create_client)
│   │                       # - RpcResult: rpc().execute() チェーン対応
│   │
│   ├── gemini.py           # （空ファイル）将来のGeminiラッパー用
│   └── line.py             # （空ファイル）将来のLINEラッパー用
│
├── scripts/
│   ├── init_db.py          # SQLiteテーブル初期化
│   │                       # - chat_histories テーブル作成
│   │                       # - line_user_id インデックス作成
│   │
│   └── test_endpoints.py   # エンドポイント結合テスト
│                           # - Webhook → Worker の疎通確認
│                           # - テスト用ダミー署名・ペイロード送信
│
├── run_tests.py            # 統合テストランナー
│                           # - サーバー自動起動・停止
│                           # - ヘルスチェック付き
│                           # - ENV=test で環境設定
│
├── requirements.txt        # Python依存パッケージ一覧
├── .env                    # 環境変数（本番値）
├── .env.example            # 環境変数テンプレート
├── LOCAL_TESTING.md        # ローカルテスト手順書
├── SYSTEM_SPECIFICATION.md # 本ドキュメント
├── chat_histories.db       # SQLiteデータベース（ローカル）
├── create_structure.py     # （旧）プロジェクト構成生成スクリプト
└── .gitignore              # Git除外設定
```

---

## 4. データベース設計

### 4.1 本番環境: Supabase (PostgreSQL + pgvector)

#### テーブル: `chat_histories`

| カラム | 型 | 制約 | 説明 |
|--------|------|------|------|
| `id` | `bigint` | PRIMARY KEY, AUTO INCREMENT | 自動採番ID |
| `line_user_id` | `text` | NOT NULL, INDEXED | LINEユーザーID |
| `role` | `text` | NOT NULL, CHECK ('user', 'model') | 発言者種別 |
| `content` | `text` | NOT NULL | メッセージ本文 |
| `embedding` | `vector(768)` | - | 768次元ベクトル（gemini-embedding-001） |
| `created_at` | `timestamptz` | DEFAULT now() | 作成日時 |

#### RLS (Row Level Security)
RLSの詳細な設定はコードベース上に定義なし。Supabaseコンソール上で設定されている可能性あり。

#### ストアドプロシージャ（RPC）

**`search_similar_chats`**
- 入力: `user_id` (text), `query_embedding` (vector(768)), `match_count` (int)
- 処理: コサイン類似度で `chat_histories` から類似会話を検索
- 戻り値: 類似度順にソートされた会話履歴

### 4.2 ローカル開発環境: SQLite

`chat_histories.db` として保存。`lib/supabase.py` 内の `SupabaseClient` が `__new__` 時にテスト環境を検出して自動的にSQLiteモックに切り替わる。

#### テーブル: `chat_histories`

| カラム | 型 | 制約 | 説明 |
|--------|------|------|------|
| `id` | `INTEGER` | PRIMARY KEY AUTOINCREMENT | 自動採番ID |
| `line_user_id` | `TEXT` | NOT NULL, INDEXED | LINEユーザーID |
| `role` | `TEXT` | NOT NULL, CHECK ('user', 'model') | 発言者種別 |
| `content` | `TEXT` | NOT NULL | メッセージ本文 |
| `embedding` | `TEXT` | - | JSON配列として保存（768次元） |
| `created_at` | `TIMESTAMP` | DEFAULT CURRENT_TIMESTAMP | 作成日時 |

類似検索はSQLite側でnumpyを用いたコサイン類似度計算を実装。

---

## 5. 外部API連携仕様

### 5.1 LINE Messaging API

| 項目 | 仕様 |
|------|------|
| **Webhook受信** | Vercel Webhook (`/api/webhook`) にPOST。署名は `LINE_CHANNEL_SECRET` とHMAC-SHA256で検証 |
| **返信方法** | **Reply API**（`POST /v2/bot/message/reply`）← Push APIから移行済み |
| **アクセストークン** | 環境変数 `LINE_CHANNEL_ACCESS_TOKEN` を使用（`LINE_ACCESS_TOKEN` は不使用） |
| **返信形式** | `{'replyToken': reply_token, 'messages': [{'type': 'text', 'text': message}]}` |
| **制約** | replyTokenは1回使い切り、有効期限あり |

#### Webhookペイロード構造
```json
{
  "events": [{
    "type": "message",
    "replyToken": "xxxxxxxx",
    "source": {"userId": "LINE_USER_ID"},
    "message": {"type": "text", "text": "ユーザーメッセージ"}
  }]
}
```

### 5.2 Google Gemini API

| 項目 | 仕様 |
|------|------|
| **APIキー** | 環境変数 `GEMINI_API_KEY` |
| **テキスト生成モデル** | `gemini-2.5-flash-lite`（無料枠のデイリー制限回避のため軽量モデル） |
| **埋め込みモデル** | `models/gemini-embedding-001`（768次元、Supabaseのカラム定義と整合） |
| **埋め込みAPI** | `genai.embed_content(model='models/gemini-embedding-001', content=text, task_type='retrieval_query')` |
| **テキスト生成API** | `generation_model.generate_content(full_prompt)` |

### 5.3 Upstash QStash

| 項目 | 仕様 |
|------|------|
| **用途** | Vercelの10秒タイムアウト回避のための非同期メッセージキュー |
| **エンドポイント** | `https://qstash-us-east-1.upstash.io/v2/publish/{worker_url}` |
| **認証** | Bearer Token（環境変数 `QSTASH_TOKEN`） |
| **データ構造** | `{'line_user_id': ..., 'text': ..., 'reply_token': ...}` をそのまま転送 |
| **Worker URL** | `https://line-bot-cwlc.vercel.app/api/worker`（ハードコード） |
| **バリデーション** | QStash署名検証用キー: `QSTASH_CURRENT_SIGNING_KEY`, `QSTASH_NEXT_SIGNING_KEY` |

---

## 6. 現在の仕様上の制約と課題

### 技術的制約

| # | 制約 | 詳細 | 対策 |
|---|------|------|------|
| 1 | **Vercel 10秒タイムアウト** | Serverless Functionsの最大実行時間が10秒。Gemini API + DB処理では超過する可能性あり | QStashで非同期キューイングし、Worker関数で処理 |
| 2 | **Reply Tokenの有効期限** | LINE Reply APIのreplyTokenは1回使い切り＋短い有効期限。Gemini生成が遅いと期限切れ | エラーログを出力して原因特定可能に。同期処理で極力遅延を減らす |
| 3 | **LINE無料枠制限** | Push APIは月200通制限。Reply APIは無制限 | Reply APIに完全移行済み |
| 4 | **Gemini無料枠制限** | 1日20回の厳格な制限 | `gemini-2.5-flash-lite`（軽量モデル）を使用して節約 |
| 5 | **Embedding次元数の固定** | pgvectorのカラム定義は768次元固定。異なる次元のモデルを使うと `22000` エラー | `gemini-embedding-001`（768次元）に固定 |

### 現在の課題

1. **Gemini APIキー有効期限切れ**: `.env` に設定されている `GEMINI_API_KEY` が期限切れ。テスト時は `test_key` で代替するが、本番復旧には新しいAPIキーが必要
2. **LOCAL_TESTING.mdの更新不足**: Push API→Reply API移行後のテスト手順が未反映。Reply APIではreplyTokenが必須であることを明記すべき
3. **空ファイルの存在**: `lib/gemini.py`, `lib/line.py` が空。将来的なリファクタリングで機能集約が想定されるが、現状未実装
4. **webhook.pyのデッドコード**: `verify_signature` 関数内に到達不能コード（行20-29）が存在。リファクタリングで削除推奨
5. **テスト環境の環境変数継承問題**: `start /b` コマンドで子プロセスに `ENV=test` が継承されない。コード内のテスト判定が環境変数に依存しており不安定
6. **Supabase接続**: `SUPABASE_SERVICE_ROLE_KEY` がダミー値のため、本番Supabaseへの接続は未検証
