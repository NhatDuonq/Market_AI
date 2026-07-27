import subprocess
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/run-crawler', methods=['POST'])
def run_crawler():
    try:
        # Sử dụng Popen để kích hoạt file shell chạy ngầm dưới nền hệ thống
        # n8n sẽ không cần phải đứng đợi script chạy xong nữa
        subprocess.Popen(['/bin/bash', '/opt/market-ai/crawler/run_market_ai.sh'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return jsonify({
            "status": "success",
            "message": "Market AI Crawler started running in background successfully!"
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
