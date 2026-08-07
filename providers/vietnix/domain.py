import os
import sys
import re
import json
import random
from datetime import datetime
import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Import core modules
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.base_provider import BaseProvider
from core.diff_engine import DiffEngine
from core.telegram_notifier import TelegramNotifier
from core.retry_handler import retry, get_random_user_agent, random_delay

class VietnixDomainProvider(BaseProvider):
    """
    Crawler chuyên biệt cho Sản Phẩm Tên Miền Vietnix (vietnix.vn).
    Bóc tách đầy đủ: TLD, Phí Đăng Ký, Phí Gia Hạn, Phí Chuyển Đổi, Khuyến Mãi.
    """
    def __init__(self):
        super().__init__(
            provider_name="vietnix",
            base_url="https://vietnix.vn/bang-gia-ten-mien/"
        )
        self.diff_engine = DiffEngine()
        self.telegram = TelegramNotifier()

    def _parse_table_rows(self, soup) -> list:
        items = []
        tables = soup.find_all("table")
        for t in tables:
            rows = t.find_all("tr")
            for r in rows:
                cols = r.find_all(["td", "th"])
                if len(cols) < 2:
                    continue

                col0_text = cols[0].get_text(" ", strip=True)
                tld_match = re.search(r'(\.[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)?)', col0_text)
                if not tld_match:
                    continue

                tld = tld_match.group(1).lower()
                if tld.endswith("."):
                    tld = tld[:-1]

                col1 = cols[1]
                old_tag = col1.find(class_='text_price_old')
                new_tag = col1.find(class_='text_price_new')

                if new_tag:
                    reg_price = float(re.sub(r'[^\d]', '', new_tag.get_text()))
                    reg_price_orig = float(re.sub(r'[^\d]', '', old_tag.get_text())) if old_tag else None
                else:
                    prices = [float(p.replace('.', '').replace(',', '')) for p in re.findall(r'([\d\.\,]+)\s*đ', col1.get_text(' ', strip=True))]
                    reg_price = prices[0] if prices else 0.0
                    reg_price_orig = None

                renew_price = 0.0
                if len(cols) > 2:
                    col2 = cols[2]
                    renew_prices = [float(p.replace('.', '').replace(',', '')) for p in re.findall(r'([\d\.\,]+)\s*đ', col2.get_text(' ', strip=True))]
                    renew_price = renew_prices[-1] if renew_prices else reg_price
                else:
                    renew_price = reg_price

                if reg_price > 0 or renew_price > 0:
                    item = {
                        "tld": tld,
                        "register_price": reg_price,
                        "renew_price": renew_price if renew_price > 0 else reg_price,
                        "transfer_price": reg_price,
                        "promo_note": ""
                    }
                    if reg_price_orig and reg_price_orig > reg_price:
                        item["register_price_original"] = reg_price_orig

                    items.append(item)
        return items

    @retry(max_attempts=3, backoff_factor=2.0)
    def scrape_domain_pricing_bs4(self) -> list:
        """
        Bóc tách nhanh qua HTTP Requests + BeautifulSoup.
        """
        print(f"⚡ [{self.provider_name.upper()}-DOMAIN] Thử bóc tách nhanh qua HTTP/BS4...")
        items = []
        try:
            ua = get_random_user_agent()
            res = requests.get(self.base_url, headers={
                "User-Agent": ua,
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8"
            }, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                items = self._parse_table_rows(soup)
        except Exception as e:
            print(f"⚠️ HTTP/BS4 Error: {e}")
        return items

    def scrape_domain_pricing_playwright(self) -> tuple[list, str]:
        """
        Bóc tách bằng Playwright (Render JS + Screenshot).
        """
        from playwright.sync_api import sync_playwright
        print(f"🚀 [{self.provider_name.upper()}-DOMAIN] Bắt đầu cào dữ liệu Playwright...")
        items = []
        screenshot_dir = os.path.join(project_root, "storage", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"vietnix_domain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        with sync_playwright() as p:
            browser, context, page = self.launch_browser(p)
            try:
                page.goto(self.base_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(2000, 3000))

                try:
                    page.screenshot(path=screenshot_path, full_page=False)
                    print(f"📸 Đã chụp ảnh màn hình giao diện: {screenshot_path}")
                except Exception as e_ss:
                    print(f"⚠️ Không thể chụp screenshot: {e_ss}")

                # Use BS4 on rendered page content
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                items = self._parse_table_rows(soup)
            except Exception as e:
                print(f"⚠️ Playwright Error: {e}")
            finally:
                context.close()
                browser.close()

        return items, screenshot_path

    def scrape_domain_pricing(self) -> tuple[list, str]:
        items = []
        screenshot_path = ""

        try:
            items, screenshot_path = self.scrape_domain_pricing_playwright()
        except Exception as e:
            print(f"⚠️ Lỗi Playwright ({e}), chuyển sang dùng HTTP/BS4...")

        if not items:
            items = self.scrape_domain_pricing_bs4()

        unique_items = {}
        for it in items:
            tld = it["tld"]
            if tld not in unique_items or (it["register_price"] > 0 and unique_items[tld]["register_price"] == 0):
                unique_items[tld] = it

        final_list = list(unique_items.values())
        print(f"✅ [{self.provider_name.upper()}-DOMAIN] Đã thu thập {len(final_list)} đuôi tên miền.")
        return final_list, screenshot_path

    def run(self, force_notify: bool = False):
        domain_items, screenshot_path = self.scrape_domain_pricing()
        
        if not domain_items:
            print(f"⚠️ [{self.provider_name.upper()}-DOMAIN] Không lấy được dữ liệu tên miền nào.")
            return

        diff_res = self.diff_engine.compare_domain_data("vietnix_domain", domain_items, url=self.base_url)

        has_changes = diff_res.get("has_changes", False)
        should_notify = force_notify or has_changes

        report_msg = self.telegram.format_domain_diff_report("Vietnix (Tên miền)", diff_res)

        if should_notify:
            print(f"\n🔔 [{self.provider_name.upper()}-DOMAIN] {'[CẢNH BÁO BIẾN ĐỘNG]' if has_changes else '[GỬI BÁO CÁO THỦ CÔNG/ĐỊNH KỲ]'} -> Đang gửi báo cáo...")
            print("--- NỘI DUNG BÁO CÁO TELEGRAM ---")
            print(report_msg)
            print("---------------------------------\n")

            if self.telegram.is_configured():
                self.telegram.send_message(report_msg)
                if os.path.exists(screenshot_path):
                    self.telegram.send_photo(screenshot_path, caption="📸 Screenshot giao diện Vietnix Tên miền hiện tại")

            try:
                from core.email_notifier import EmailNotifier
                email = EmailNotifier()
                if email.is_configured():
                    html_body = email.format_domain_report_html("VIETNIX", diff_res)
                    email.send_report(
                        subject=f"[Market AI] {'🚨 [CẢNH BÁO] Biến Động Giá' if has_changes else '📊 Báo Cáo Cạnh Tranh'} - VIETNIX - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                        html_body=html_body,
                        screenshot_paths=[screenshot_path] if (screenshot_path and os.path.exists(screenshot_path)) else []
                    )
            except Exception as e:
                print(f"⚠️ Lỗi gửi email Vietnix: {e}")
        else:
            print(f"ℹ️ [{self.provider_name.upper()}-DOMAIN] Quét định kỳ thành công: Bảng giá ổn định (không có biến động). Bỏ qua gửi báo cáo để tránh spam.")

if __name__ == "__main__":
    provider = VietnixDomainProvider()
    provider.run()
