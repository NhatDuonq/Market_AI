import os
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.telegram_notifier import TelegramNotifier

def run_full_demo_simulation():
    notifier = TelegramNotifier()

    if not notifier.is_configured():
        print("❌ Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID!")
        return

    print("🚀 Đang khởi tạo chuỗi báo cáo GIẢ LẬP DEMO cho tất cả 3 danh mục sản phẩm (Domain, Hosting, VPS)...")

    # 1. DEMO DOMAIN
    domain_demo = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": "https://www.matbao.net/ten-mien/bang-gia-ten-mien.html",
        "ui_changed": True,
        "new_tlds": [
            {"tld": ".ai", "register_price": 1850000.0, "renew_price": 1850000.0, "longvan_register_price": 1800000.0}
        ],
        "price_changes": [
            {
                "tld": ".com",
                "field": "Giá đăng ký năm đầu",
                "old_price": 289000.0,
                "new_price": 239000.0,
                "longvan_price": 290000.0,
                "diff_vs_longvan": -51000.0,
                "status_vs_longvan": "CHEAPER"
            },
            {
                "tld": ".vn",
                "field": "Giá gia hạn",
                "old_price": 450000.0,
                "new_price": 490000.0,
                "longvan_price": 340000.0,
                "diff_vs_longvan": 150000.0,
                "status_vs_longvan": "EXPENSIVE"
            }
        ],
        "longvan_summary": {
            "cheaper_count": 5,
            "expensive_count": 11,
            "cheaper_items": [{"tld": ".com", "field": "Giá đăng ký", "competitor_price": 239000.0, "longvan_price": 290000.0, "status": "CHEAPER"}],
            "expensive_items": [{"tld": ".vn", "field": "Giá gia hạn", "competitor_price": 490000.0, "longvan_price": 340000.0, "status": "EXPENSIVE"}]
        }
    }

    # 2. DEMO HOSTING
    hosting_demo = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": "https://www.matbao.net/hosting.html",
        "ui_changed": True,
        "new_plans": [
            {"plan_name": "Ultra NVMe Business", "monthly_price": 249000.0, "longvan_monthly_price": 220000.0}
        ],
        "price_changes": [
            {
                "plan_name": "Cloud Hosting Basic",
                "field": "Giá thuê tháng",
                "old_price": 65000.0,
                "new_price": 45000.0,
                "longvan_price": 49000.0,
                "diff_vs_longvan": -4000.0,
                "status_vs_longvan": "CHEAPER"
            },
            {
                "plan_name": "Cloud Hosting Pro",
                "field": "Giá thuê tháng",
                "old_price": 89000.0,
                "new_price": 105000.0,
                "longvan_price": 99000.0,
                "diff_vs_longvan": 6000.0,
                "status_vs_longvan": "EXPENSIVE"
            }
        ],
        "longvan_summary": {
            "cheaper_count": 2,
            "expensive_count": 3,
            "cheaper_items": [{"plan_name": "Cloud Hosting Basic", "competitor_price": 45000.0, "longvan_price": 49000.0, "status": "CHEAPER"}],
            "expensive_items": [{"plan_name": "Cloud Hosting Pro", "competitor_price": 105000.0, "longvan_price": 99000.0, "status": "EXPENSIVE"}]
        }
    }

    # 3. DEMO VPS
    vps_demo = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": "https://www.matbao.net/cloud-vps.html",
        "ui_changed": False,
        "new_plans": [],
        "price_changes": [
            {
                "plan_name": "Cloud VPS Entry (2 Core, 2GB)",
                "field": "Giá VPS tháng",
                "old_price": 140000.0,
                "new_price": 110000.0,
                "longvan_price": 120000.0,
                "diff_vs_longvan": -10000.0,
                "status_vs_longvan": "CHEAPER"
            },
            {
                "plan_name": "Cloud VPS Standard (4 Core, 4GB)",
                "field": "Giá VPS tháng",
                "old_price": 230000.0,
                "new_price": 260000.0,
                "longvan_price": 240000.0,
                "diff_vs_longvan": 20000.0,
                "status_vs_longvan": "EXPENSIVE"
            }
        ],
        "longvan_summary": {
            "cheaper_count": 1,
            "expensive_count": 2,
            "cheaper_items": [{"plan_name": "Cloud VPS Entry", "competitor_price": 110000.0, "longvan_price": 120000.0, "status": "CHEAPER"}],
            "expensive_items": [{"plan_name": "Cloud VPS Standard", "competitor_price": 260000.0, "longvan_price": 240000.0, "status": "EXPENSIVE"}]
        }
    }

    simulations = [
        ("domain", "Mắt Bão", domain_demo, "📸 Screenshot Giao diện Mắt Bão Tên miền (Giả lập DEMO)"),
        ("hosting", "Mắt Bão", hosting_demo, "📸 Screenshot Giao diện Mắt Bão Web Hosting (Giả lập DEMO)"),
        ("vps", "Mắt Bão", vps_demo, "📸 Screenshot Giao diện Mắt Bão Cloud VPS (Giả lập DEMO)")
    ]

    for p_type, p_name, demo_data, photo_caption in simulations:
        report_msg = notifier.format_diff_report(p_name, p_type, demo_data, is_demo=True)
        print(f"\n📤 Đang gửi bản tin DEMO [{p_type.upper()}] + Ảnh screenshot tới Telegram...")
        notifier.send_report_with_photo(report_msg, caption=photo_caption)

    print("\n==================================================")
    print("✅ ĐÃ GỬI HOÀN TẤT BỘ BÁO CÁO GIẢ LẬP DEMO (DOMAIN, HOSTING, VPS) TỚI TELEGRAM!")

if __name__ == "__main__":
    run_full_demo_simulation()
