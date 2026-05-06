import os
import sqlite3
import numpy as np
import json

class RpcResult:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return self

class SupabaseClient:
    """
    テスト環境（ENV=test またはダミーAPIキー）ではSQLiteモックを使用。
    本番環境では本物のSupabaseクライアントを使用。
    """
    def __new__(cls):
        # テスト環境またはダミーキーの場合はSQLiteモックを使用
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
        if os.getenv('ENV') == 'test' or 'test' in key or 'sb_secret' in key:
            instance = super().__new__(cls)
            instance.conn = sqlite3.connect('chat_histories.db')
            return instance
        
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL または SUPABASE_SERVICE_ROLE_KEY が環境変数に設定されていません。")
        
        return create_client(url, key)
    
    # ---- SQLiteモック用メソッド ----
    def get_recent_chats(self, user_id, limit=6):
        """直近の会話履歴を時系列順（新しい順）で取得"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            SELECT role, content, created_at
            FROM chat_histories
            WHERE line_user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """, (user_id, limit))
            results = []
            for row in cursor.fetchall():
                results.append({
                    'role': row[0],
                    'content': row[1],
                    'created_at': row[2]
                })
            results.reverse()  # 古い順に並び替え
            return results
        except Exception as e:
            print(f"直近履歴取得エラー: {str(e)}")
            return []

    def rpc(self, func_name, params):
        if func_name == 'search_similar_chats':
            embedding = params['query_embedding']
            if isinstance(embedding, str):
                embedding = json.loads(embedding)
            result = self.search_similar_chats(
                params['user_id'],
                embedding,
                params['match_count']
            )
            return RpcResult(result)
        return RpcResult([])
    
    def search_similar_chats(self, user_id, embedding, limit=5):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            SELECT id, line_user_id, role, content, embedding
            FROM chat_histories
            WHERE line_user_id = ?
            """, (user_id,))
            results = []
            for row in cursor.fetchall():
                if row[4]:
                    emb = json.loads(row[4])
                    similarity = np.dot(embedding, emb) / (np.linalg.norm(embedding) * np.linalg.norm(emb))
                    results.append({
                        'id': row[0],
                        'line_user_id': row[1],
                        'role': row[2],
                        'content': row[3],
                        'similarity': similarity
                    })
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:limit]
        except Exception as e:
            print(f"検索エラー: {str(e)}")
            return []
    
    def table(self, table_name):
        return self
    
    def insert(self, data):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO chat_histories 
            (line_user_id, role, content, embedding)
            VALUES (?, ?, ?, ?)
            """, (
                data['line_user_id'],
                data['role'],
                data['content'],
                json.dumps(data['embedding']) if 'embedding' in data else None
            ))
            self.conn.commit()
        except Exception as e:
            print(f"挿入エラー: {str(e)}")
        return self
    
    def execute(self):
        return self
