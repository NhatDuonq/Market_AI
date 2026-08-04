import os
import sys
import re
import json
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")

class BaseProvider:
    """
    Lớp cơ sở cho toàn bộ các Provider Crawler đối thủ và sản phẩm (Domain, Hosting, VPS).
    """
    def __init__(self, provider_name: str, base_url: str, product_type: str = "domain"):
        self.provider_name = provider_name
        self.base_url = base_url
        self.product_type = product_type

    def get_db_connection(self):
        return psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )

    def clean_price(self, price_str: str) -> float:
        """
        Chuẩn hóa chuỗi giá thành dạng số thực (VND).
        Ví dụ: "150.000 đ/tháng" -> 150000.0
        Đặc biệt: Xử lý ô giá có cả giá gạch (cũ) và giá KM (mới), lấy giá mới nhất.
        """
        if not price_str:
            return 0.0
        
        # Nếu có nhiều dòng text (ví dụ: dòng 1 giá gạch 350.000đ, dòng 2 giá KM 150.000đ)
        # lấy dòng cuối cùng (giá KM áp dụng thực tế)
        lines = [l.strip() for l in str(price_str).splitlines() if l.strip()]
        target_str = lines[-1] if lines else str(price_str)
        
        # Tìm cụm giá có dạng XXX.XXX hoặc XXX.XXX.XXXđ
        price_matches = re.findall(r'\b\d{1,3}(?:\.\d{3})+\b|\b\d{4,8}\b', target_str)
        if price_matches:
            target_str = price_matches[-1]

        cleaned = re.sub(r'[^\d]', '', target_str)
        try:
            val = float(cleaned) if cleaned else 0.0
            if val > 50000000:
                # Nếu số > 50 triệu (do lỗi nối văn bản), lấy mẫu match đầu tiên phù hợp giá tên miền
                matches = re.findall(r'\d{1,3}(?:\.\d{3})+', str(price_str))
                if matches:
                    val = float(re.sub(r'[^\d]', '', matches[0]))
            return val
        except ValueError:
            return 0.0

    def add_vat(self, price: float, vat_rate: float = 0.10) -> float:
        """
        Thêm VAT vào giá chưa thuế.
        """
        return round(price * (1 + vat_rate), 2)

    def save_change_logs(self, records: list):
        """
        So sánh dữ liệu giá/thông số cũ và mới. Chỉ INSERT khi phát hiện có biến động.
        Sử dụng try/except/finally đảm bảo rollback khi lỗi và close connection luôn được gọi.
        """
        if not records:
            print(f"[{self.provider_name}] Không có bản ghi nào để lưu.")
            return

        conn = None
        try:
            conn = self.get_db_connection()
            cur = conn.cursor()
            inserted_count = 0

            for item in records:
                obj_name = item.get("object_name")
                new_val = str(item.get("new_data"))

                cur.execute("""
                    SELECT new_data 
                    FROM change_logs 
                    WHERE provider = %s AND object_name = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1;
                """, (self.provider_name, obj_name))

                row = cur.fetchone()
                last_val = row[0] if row else None
                if isinstance(last_val, str):
                    last_val = last_val.strip('"')

                if last_val is None:
                    old_val = "0"
                    should_save = True
                elif last_val != new_val:
                    old_val = last_val
                    should_save = True
                else:
                    should_save = False

                if should_save:
                    cur.execute("""
                        INSERT INTO change_logs (object_name, change_type, old_data, new_data, created_at, provider, url)
                        VALUES (%s, %s, %s::json, %s::json, %s, %s, %s)
                    """, (
                        obj_name,
                        item.get("change_type", "PRICE_CHANGE"),
                        json.dumps(old_val),
                        json.dumps(new_val),
                        datetime.now(),
                        self.provider_name,
                        item.get("url", self.base_url)
                    ))
                    inserted_count += 1

            conn.commit()
            cur.close()
            print(f"[{self.provider_name}] Hoàn tất. Đã lưu {inserted_count} bản ghi biến động giá mới vào DB.")
        except Exception as e:
            print(f"[{self.provider_name}] Lỗi lưu DB change_logs: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def launch_browser(self, playwright):
        """
        Khởi tạo trình duyệt Playwright với Stealth Anti-bot Headers.
        - User-Agent được rotate ngẫu nhiên từ pool 12 UA.
        - Random delay trước khi bắt đầu scrape.
        """
        from core.retry_handler import get_random_user_agent, random_delay

        ua = get_random_user_agent()
        print(f"[{self.provider_name}] 🕵️ UA: {ua[:50]}...")

        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=ua,
            locale="vi-VN",
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            extra_http_headers={
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        )
        page = context.new_page()

        # Anti-detect: Override navigator.webdriver
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        return browser, context, page
