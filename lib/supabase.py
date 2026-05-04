import sqlite3
import numpy as np
import json

class RpcResult:
    def __init__(self, data):
        self.data = data
    
    def execute(self):
        return self

class SupabaseClient:
    def __init__(self):
        self.conn = sqlite3.connect('chat_histories.db')
    
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
            
            # 簡易的なコサイン類似度計算
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
            
            # 類似度でソート
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
