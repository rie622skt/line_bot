import os
from supabase import create_client

class SupabaseClient:
    """
    以前のSQLiteモックと同じように client = SupabaseClient() と呼び出せるようにしつつ、
    中身はクラウド上の本物のSupabaseクライアントを返すようにする設計です。
    """
    def __new__(cls):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL または SUPABASE_SERVICE_ROLE_KEY が環境変数に設定されていません。")
            
        return create_client(url, key)