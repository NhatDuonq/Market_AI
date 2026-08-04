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
    snap_dir = os.path.join(project_root, "storage", "snapshots")
    ss_dir = os.path.join(project_root, "storage", "screenshots")

    # Collect snapshots
    report_text_lines = ["📊 BÁO CÁO TỔNG HỢP GIÁ TÊN MIỀN CANH TRẠNH\n"]
    screenshots = []

    for p in providers:
        pkey = f"{p}_domain"
        snap = diff_engine.load_last_snapshot(pkey)
        if snap and snap.get("items"):
            items = snap["items"]
            # 3-way diff result
            diff_res = diff_engine.compare_domain_data(pkey, items, url=snap.get("url", ""), save=False)

            # Format Telegram summary
            report_text_lines.append(telegram.format_domain_diff_report(p.upper(), diff_res))
            report_text_lines.append("\n" + "═" * 30 + "\n")

            # Find latest screenshot
            pattern_ss = os.path.join(ss_dir, f"{p}_domain_*.png")
            import glob
            files = glob.glob(pattern_ss)
            if files:
                latest_ss = max(files, key=os.path.getmtime)
                screenshots.append(latest_ss)

            # Send Email if configured
            if email_ready:
                html_body = email_notifier.format_domain_report_html(p.upper(), diff_res)
                email_notifier.send_report(
                    subject=f"[Market AI] Báo Cáo Cạnh Tranh Tên Miền - {p.upper()} - {datetime.now().strftime('%d/%m/%Y')}",
                    html_body=html_body,
                    screenshot_paths=screenshots
                )
                if "Email" not in sent_channels:
                    sent_channels.append("Email")

    # Send Telegram if configured
    if tg_ready:
        full_msg = "\n".join(report_text_lines)
        if len(full_msg) > 3800:
            full_msg = full_msg[:3700] + "\n\n... (Đã cắt bớt vì quá dài)\n✅ Báo cáo đầy đủ xem tại Dashboard"
        telegram.send_message(full_msg)

        # Send latest screenshot if available
        if screenshots:
            telegram.send_photo(screenshots[0], caption="📸 Ảnh đối soát giá gần nhất")

        sent_channels.append("Telegram")

    channels_str = " & ".join(sent_channels)
    print(json.dumps({
        "success": True,
        "message": f"Đã gửi báo cáo thành công qua {channels_str}!"
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
