import os

# 主要ディレクトリの作成
dirs = ['api', 'lib', 'scripts']
for d in dirs:
    os.makedirs(d, exist_ok=True)

# 主要ファイルの作成（既存ファイルは上書きしない）
files_to_create = [
    'api/webhook.py',
    'api/worker.py',
    'lib/gemini.py',
    'lib/supabase.py',
    'lib/line.py',
    'scripts/init_db.py'
]

for file_path in files_to_create:
    if not os.path.exists(file_path):
        open(file_path, 'w').close()