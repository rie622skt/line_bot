import os
import sys
import subprocess
import time
import requests

# プロジェクト設定
PROJECT_ROOT = os.getcwd()
WEBHOOK_CMD = "python api/webhook.py"
WORKER_CMD = "python api/worker.py"
TEST_CMD = "python scripts/test_endpoints.py"

# 環境設定
os.environ['ENV'] = 'test'
os.environ['LINE_CHANNEL_SECRET'] = 'test_secret'
os.environ['GEMINI_API_KEY'] = 'test_key'
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
os.environ['PYTHONPATH'] = PROJECT_ROOT

# サーバープロセスを開始
def start_server(cmd, name):
    print(f"Starting {name} server...")
    log_file = open(f"{name}_server.log", "w")
    return subprocess.Popen(
        cmd,
        shell=True,
        cwd=PROJECT_ROOT,
        stdout=log_file,
        stderr=log_file
    )

# サーバーの起動を確認
def wait_for_server(url, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code < 500:
                return True
        except:
            pass
        time.sleep(0.5)
    return False

# メイン実行
def main():
    # サーバー起動
    webhook_proc = start_server(WEBHOOK_CMD, "Webhook")
    worker_proc = start_server(WORKER_CMD, "Worker")
    
    # サーバー起動待機
    print("Waiting for servers to start...")
    if not wait_for_server("http://localhost:5000"):
        print("Webhook server failed to start")
        return 1
    
    # Give worker server extra time to start
    print("Waiting extra time for worker server...")
    time.sleep(5)
    
    if not wait_for_server("http://localhost:5001", timeout=20):
        print("Worker server failed to start")
        return 1
    
    # テスト実行
    print("Running tests...")
    test_result = subprocess.run(TEST_CMD, shell=True, cwd=PROJECT_ROOT)
    
    # サーバー停止
    print("Stopping servers...")
    webhook_proc.terminate()
    worker_proc.terminate()
    
    return test_result.returncode

if __name__ == "__main__":
    sys.exit(main())