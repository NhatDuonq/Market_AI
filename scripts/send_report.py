import os
import sys
import json
import glob
import base64
import argparse
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
    parser = argparse.ArgumentParser(description="Send market AI competitive report")
    parser.add_argument("--channel", default="all", choices=["all", "email", "telegram"], help="Target channel")
    parser.add_argument("--email", default=None, help="Target email recipient")
    parser.add_argument("--cc", default="", help="Comma separated list of CC emails")
    parser.add_argument("--payload", default=None, help="Base64 encoded JSON payload")

    args = parser.parse_args()

    target_channel = args.channel
    target_email = args.email
    cc_emails = [c.strip() for c in args.cc.split(",") if c.strip()]

    if args.payload:
        try:
            decoded = json.loads(base64.b64decode(args.payload.encode('utf-8')).decode('utf-8'))
            target_channel = decoded.get("channel", target_channel)
            target_email = decoded.get("target_email", target_email)
            cc_emails = decoded.get("cc_emails", cc_emails)
        except Exception as e:
            pass

    diff_engine = DiffEngine()
    telegram = TelegramNotifier()
    email_notifier = EmailNotifier()

    tg_ready = telegram.is_configured() and (target_channel in ["all", "telegram"])
    email_ready = target_channel in ["all", "email"]

    if not tg_ready and not email_ready:
        print(json.dumps({
            "error": "Kênh nhận báo cáo được chọn chưa sẵn sàng hoặc chưa được cấu hình!"
        }, ensure_ascii=False))
        sys.exit(1)

    sent_channels = []
    providers = ["matbao", "pavietnam", "vietnix"]
    ss_dir = os.path.join(project_root, "storage", "screenshots")
    dashboard_url = os.getenv("DASHBOARD_URL", "https://thitruong.longvan.net")

    for p in providers:
        pkey = f"{p}_domain"
        snap = diff_engine.load_last_snapshot(pkey)
        if snap and snap.get("items"):
            items = snap["items"]
            diff_res = diff_engine.compare_domain_data(pkey, items, url=snap.get("url", ""), save=False)

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
                    screenshot_paths=[p_ss] if (p_ss and os.path.exists(p_ss)) else [],
                    to_email=target_email,
                    cc_emails=cc_emails
                )
                if "Email" not in sent_channels:
                    sent_channels.append("Email")

    channels_str = " & ".join(sent_channels)
    recipient_info = f" (Email: {target_email})" if target_email else ""
    cc_info = f" [CC: {', '.join(cc_emails)}]" if cc_emails else ""

    print(json.dumps({
        "success": True,
        "message": f"Đã gửi báo cáo thị trường qua {channels_str}{recipient_info}{cc_info} thành công!"
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
