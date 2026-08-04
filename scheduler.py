import os
import sys
import threading
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

from main import run_all, run_specific

INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", "30"))
INTERVAL_SECONDS = int(os.getenv("CRAWL_INTERVAL_SECONDS", "0"))

app = Flask(__name__)
scheduler = BackgroundScheduler()

@app.route("/trigger/all", methods=["POST"])
def trigger_all():
    """Trigger quét tất cả ngay lập tức (chạy ngầm trong thread riêng)"""
    threading.Thread(target=run_all).start()
    return jsonify({"status": "success", "message": "Đã kích hoạt quét tất cả mục tiêu."}), 200

@app.route("/trigger/<provider>/<product>", methods=["POST"])
def trigger_specific(provider, product):
    """Trigger quét mục tiêu cụ thể ngay lập tức"""
    threading.Thread(target=run_specific, args=(provider, product)).start()
    return jsonify({"status": "success", "message": f"Đã kích hoạt quét {provider} - {product}."}), 200

def run_morning_report():
    print("☀️ [BẢN TIN SÁNG 8H00] Bắt đầu lượt quét và phát báo cáo sáng cho ban quản trị...")
    run_all(force_notify=True)

def start_scheduled_loop():
    print(f"🚀 [MARKET-AI SCHEDULER] Đã khởi chạy bằng APScheduler.")
    if INTERVAL_SECONDS > 0:
        print(f"⏱️ Tần suất quét ngầm (TEST): Mỗi {INTERVAL_SECONDS} GIÂY (Chỉ cảnh báo khi CÓ BIẾN ĐỘNG GIÁ).")
        job_kwargs = {"trigger": "interval", "seconds": INTERVAL_SECONDS}
    else:
        print(f"⏱️ Tần suất quét ngầm: Mỗi {INTERVAL_MINUTES} PHÚT (Chỉ cảnh báo khi CÓ BIẾN ĐỘNG GIÁ).")
        job_kwargs = {"trigger": "interval", "minutes": INTERVAL_MINUTES}

    # 1. Quét định kỳ ngầm (im lặng trừ khi có biến động giá/TLD mới)
    scheduler.add_job(
        func=lambda: run_all(force_notify=False),
        id="run_all_job",
        name="Quét tất cả nhà cung cấp định kỳ (Silent Mode)",
        replace_existing=True,
        next_run_time=datetime.now(), # Lần đầu chạy ngay
        **job_kwargs
    )

    # 2. Bản tin sáng 8h00 hàng ngày (Luôn phát báo cáo để báo hệ thống sống khỏe)
    scheduler.add_job(
        func=run_morning_report,
        trigger="cron",
        hour=8,
        minute=0,
        id="morning_report_job",
        name="Bản tin sáng 8h00 định kỳ",
        replace_existing=True
    )
    print("⏰ Đã lên lịch [BẢN TIN SÁNG] tự động phát lúc 08:00 AM hàng ngày.")

    scheduler.start()
    
    # Khởi chạy Flask server để lắng nghe API trigger
    # Chạy ở port 5001 để tránh trùng (tuỳ chọn)
    port = int(os.getenv("SCHEDULER_PORT", "5001"))
    print(f"🌐 Lắng nghe API Trigger tại http://0.0.0.0:{port}")
    try:
        app.run(host="0.0.0.0", port=port, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Đã dừng Scheduler.")
        scheduler.shutdown()

if __name__ == "__main__":
    start_scheduled_loop()
