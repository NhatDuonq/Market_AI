import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.diff_engine import DiffEngine
from core.telegram_notifier import TelegramNotifier

def send_all_reports():
    diff_engine = DiffEngine()
    notifier = TelegramNotifier()

    if not notifier.is_configured():
        print("❌ Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID!")
        return

    print("🚀 Đang khởi tạo và gửi báo cáo biến động & so sánh giá với Long Vân qua Telegram...")

    categories = [
        ("domain", "Mắt Bão (Tên miền)"),
        ("hosting", "Mắt Bão (Web Hosting)"),
        ("vps", "Mắt Bão (Cloud VPS)")
    ]

    for p_type, title in categories:
        snap = diff_engine.load_last_snapshot(f"matbao_{p_type}")
        items = snap.get("items", [])
        if items:
            diff_res = diff_engine.compare_product_data(f"matbao_{p_type}", p_type, items, url=snap.get("url", ""))
            if diff_res:
                report_msg = notifier.format_diff_report("Mắt Bão", p_type, diff_res)
                
                print(f"\n📤 Đang gửi báo cáo [{title}] đến Telegram Chat ID: {notifier.chat_id}...")
                success = notifier.send_message(report_msg)
                if success:
                    print(f"✅ Đã gửi báo cáo [{title}] thành công!")
                else:
                    print(f"❌ Gửi báo cáo [{title}] thất bại.")
        else:
            print(f"⚠️ Chưa có snapshot cho [{title}].")

if __name__ == "__main__":
    send_all_reports()
