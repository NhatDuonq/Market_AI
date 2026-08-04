import os
import sys
import json
from datetime import datetime

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from core.diff_engine import DiffEngine
from core.telegram_notifier import TelegramNotifier
from core.email_notifier import EmailNotifier


def main():
    diff_engine = DiffEngine()
    telegram = TelegramNotifier()
    email_notifier = EmailNotifier()

    tg_ready = telegram.is_configured()
    email_ready = email_notifier.is_configured()

    if not tg_ready and not email_ready:
        print(json.dumps({
            "error": "Chưa cấu hình kênh nhận báo cáo! Vui lòng điền TELEGRAM_BOT_TOKEN/CHAT_ID hoặc thông tin SMTP trong file .env"
        }, ensure_ascii=False))
        sys.exit(1)

    sent_channels = []
    providers = ["matbao", "pavietnam"]
    ss_dir = os.path.join(project_root, "storage", "screenshots")
    dashboard_url = os.getenv("DASHBOARD_URL", "https://khangthost.io.vn")

    import glob

    for p in providers:
        pkey = f"{p}_domain"
        snap = diff_engine.load_last_snapshot(pkey)
        if snap and snap.get("items"):
            items = snap["items"]
            diff_res = diff_engine.compare_domain_data(pkey, items, url=snap.get("url", ""), save=False)

            # Find latest screenshot for this provider
            pattern_ss = os.path.join(ss_dir, f"{p}_domain_*.png")
            files = glob.glob(pattern_ss)
            p_ss = max(files, key=os.path.getmtime) if files else None

            # 1. Send Telegram Message & Photo SEPARATELY for this provider
            if tg_ready:
                p_msg = telegram.format_domain_diff_report(p.upper(), diff_res)
                telegram.send_message(p_msg)

                if p_ss and os.path.exists(p_ss):
                    p_label = "Mắt Bão" if p == "matbao" else "PA Việt Nam"
                    telegram.send_photo(p_ss, caption=f"📸 Screenshot Bảng Giá Hiện Tại ({p_label})\n🔗 Xem thêm: {dashboard_url}")

                if "Telegram" not in sent_channels:
                    sent_channels.append("Telegram")

            # 2. Send Email Report for this provider
            if email_ready:
                html_body = email_notifier.format_domain_report_html(p.upper(), diff_res)
                email_notifier.send_report(
                    subject=f"[Market AI] Báo Cáo Cạnh Tranh Tên Miền - {p.upper()} - {datetime.now().strftime('%d/%m/%Y')}",
                    html_body=html_body,
                    screenshot_paths=[p_ss] if (p_ss and os.path.exists(p_ss)) else []
                )
                if "Email" not in sent_channels:
                    sent_channels.append("Email")

    channels_str = " & ".join(sent_channels)
    print(json.dumps({
        "success": True,
        "message": f"Đã gửi báo cáo riêng từng nhà cung cấp thành công qua {channels_str}!"
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
