import sqlite3
from dotenv import load_dotenv
import numpy as np
import json

load_dotenv()

def create_table():
    conn = sqlite3.connect('chat_histories.db')
    cursor = conn.cursor()
    
    # テーブル作成
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_histories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_user_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'model')),
        content TEXT NOT NULL,
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # インデックス作成
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_line_user_id 
    ON chat_histories (line_user_id);
    """)
    
    conn.commit()
    conn.close()
    print("SQLiteテーブルが正常に作成されました")

if __name__ == '__main__':
    create_table()