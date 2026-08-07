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

class MatBaoDomainProvider(BaseProvider):
    """
    Crawler chuyên biệt cho Sản Phẩm Tên Miền Mắt Bão (matbao.net).
    Bóc tách đầy đủ: TLD, Phí Đăng Ký, Phí Gia Hạn, Phí Chuyển Đổi, Khuyến Mãi.
    """
    def __init__(self):
        super().__init__(
            provider_name="matbao",
            base_url="https://www.matbao.net/ten-mien/bang-gia-ten-mien"
        )
        self.diff_engine = DiffEngine()
        self.telegram = TelegramNotifier()

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
                rows = soup.select("table tr, .price-table tr, .table-domain tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    if len(cols) >= 2:
                        col_texts = [col.get_text(strip=True) for col in cols]
                        tld_text = col_texts[0]
                        tld_match = re.search(r'(\.[\w\.]+)', tld_text)
                        if tld_match:
                            tld = tld_match.group(1).lower()
                            reg_price = self.clean_price(col_texts[1]) if len(col_texts) > 1 else 0.0
                            renew_price = self.clean_price(col_texts[2]) if len(col_texts) > 2 else reg_price
                            transfer_price = self.clean_price(col_texts[3]) if len(col_texts) > 3 else 0.0
                            if reg_price > 0 or renew_price > 0:
                                items.append({
                                    "tld": tld,
                                    "register_price": reg_price,
                                    "renew_price": renew_price,
                                    "transfer_price": transfer_price,
                                    "promo_note": col_texts[4] if len(col_texts) > 4 else ""
                                })
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
        screenshot_path = os.path.join(screenshot_dir, f"matbao_domain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        with sync_playwright() as p:
            browser, context, page = self.launch_browser(p)
            try:
                page.goto(self.base_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(2000, 4000))

                # Chụp screenshot ngay tại vị trí Bảng Giá Tên Miền
                try:
                    table_loc = page.locator("table").first
                    if table_loc.count() > 0:
                        table_loc.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                    page.screenshot(path=screenshot_path, full_page=False)
                    print(f"📸 Đã chụp ảnh màn hình giao diện bảng giá: {screenshot_path}")
                except Exception as e_ss:
                    print(f"⚠️ Không thể chụp screenshot: {e_ss}")

                # Hide popups / ads if any
                try:
                    page.evaluate("""
                        document.querySelectorAll('.modal, .popup, [class*="popup"], [id*="popup"], [class*="modal"], [class*="banner"], [id*="banner"]').forEach(e => e.remove());
                        document.body.classList.remove('modal-open');
                    """)
                except Exception:
                    pass

                rows = page.query_selector_all("table tr, .table-price tr, .domain-price-row")
                for r in rows:
                    cols = r.query_selector_all("td, th")
                    if len(cols) >= 2:
                        col_texts = [col.inner_text().strip() for col in cols]
                        tld_text = col_texts[0]
                        tld_match = re.search(r'(\.[\w\.]+)', tld_text)
                        if tld_match:
                            tld = tld_match.group(1).lower()
                            # 7-column table structure:
                            # 0: TLD, 1: Lệ phí, 2: Phí duy trì, 3: Phí QTrị 1, 4: Phí QTrị 2+, 5: Tổng năm 1, 6: Tổng năm 2+
                            if len(col_texts) >= 7:
                                reg_price = self.clean_price(col_texts[5])
                                renew_price = self.clean_price(col_texts[6])
                                reg_orig = self.clean_price(col_texts[1]) + self.clean_price(col_texts[2]) + 200000.0 * 1.08 if "666" in col_texts[5] else reg_price
                            elif len(col_texts) >= 5:
                                reg_price = self.clean_price(col_texts[4]) if self.clean_price(col_texts[4]) > 0 else (self.clean_price(col_texts[1]) + self.clean_price(col_texts[2]))
                                renew_price = self.clean_price(col_texts[2]) + self.clean_price(col_texts[3])
                                reg_orig = reg_price
                            else:
                                reg_price = self.clean_price(col_texts[1])
                                renew_price = self.clean_price(col_texts[2]) if len(col_texts) > 2 else reg_price
                                reg_orig = reg_price

                            transfer_price = 0.0  # Mat Bao offers free transfer (0 VND)
                            promo = "KM giá đăng ký" if reg_price < (renew_price + 100000) else ""

                            if reg_price > 0 or renew_price > 0:
                                items.append({
                                    "tld": tld,
                                    "register_price": reg_price,
                                    "register_price_original": reg_orig,
                                    "renew_price": renew_price,
                                    "transfer_price": transfer_price,
                                    "promo_note": promo
                                })
            except Exception as e:
                print(f"❌ Playwright Error: {e}")
            finally:
                browser.close()

        return items, screenshot_path

    def scrape_domain_pricing(self) -> tuple[list, str]:
        """
        Hybrid bóc tách: Thử Playwright trước, nếu lỗi thì dùng HTTP/BS4 fallback.
        """
        items = []
        screenshot_path = ""

        try:
            items, screenshot_path = self.scrape_domain_pricing_playwright()
        except Exception as e:
            print(f"⚠️ Lỗi Playwright ({e}), chuyển sang dùng HTTP/BS4...")

        if not items:
            items = self.scrape_domain_pricing_bs4()

        # Deduplicate TLDs
        unique_items = {}
        for it in items:
            tld = it["tld"]
            if tld not in unique_items or (it["register_price"] > 0 and unique_items[tld]["register_price"] == 0):
                unique_items[tld] = it

        final_list = list(unique_items.values())
        print(f"✅ [{self.provider_name.upper()}-DOMAIN] Đã thu thập {len(final_list)} đuôi tên miền.")
        return final_list, screenshot_path

    def run(self, force_notify: bool = False):
        """
        Luồng thực thi chính: Scrape -> Diff -> Save -> Smart Notification (Email & Telegram)
        Chỉ chủ động gửi báo cáo khi (1) Có biến động giá/TLD mới HOẶC (2) Lịch 8h00 / Ép buộc gửi (force_notify=True).
        """
        domain_items, screenshot_path = self.scrape_domain_pricing()
        
        if not domain_items:
            print(f"⚠️ [{self.provider_name.upper()}-DOMAIN] Không lấy được dữ liệu tên miền nào.")
            return

        # 1. So sánh biến động với snapshot trước
        diff_res = self.diff_engine.compare_domain_data("matbao_domain", domain_items, url=self.base_url)

        has_changes = diff_res.get("has_changes", False)
        should_notify = force_notify or has_changes

        report_msg = self.telegram.format_domain_diff_report("Mắt Bão (Tên miền)", diff_res)

        if should_notify:
            print(f"\n🔔 [{self.provider_name.upper()}-DOMAIN] {'[CẢNH BÁO BIẾN ĐỘNG]' if has_changes else '[GỬI BÁO CÁO THỦ CÔNG/ĐỊNH KỲ]'} -> Đang gửi báo cáo...")
            print("--- NỘI DUNG BÁO CÁO TELEGRAM ---")
            print(report_msg)
            print("---------------------------------\n")

            if self.telegram.is_configured():
                self.telegram.send_message(report_msg)
                if os.path.exists(screenshot_path):
                    self.telegram.send_photo(screenshot_path, caption="📸 Screenshot giao diện Mắt Bão Tên miền hiện tại")

            # Gửi báo cáo Email
            try:
                from core.email_notifier import EmailNotifier
                email = EmailNotifier()
                if email.is_configured():
                    html_body = email.format_domain_report_html("MẮT BÃO", diff_res)
                    email.send_report(
                        subject=f"[Market AI] {'🚨 [CẢNH BÁO] Biến Động Giá' if has_changes else '📊 Báo Cáo Cạnh Tranh'} - MẮT BÃO - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                        html_body=html_body,
                        screenshot_paths=[screenshot_path] if (screenshot_path and os.path.exists(screenshot_path)) else []
                    )
            except Exception as e:
                print(f"⚠️ Lỗi gửi email Mắt Bão: {e}")
        else:
            print(f"ℹ️ [{self.provider_name.upper()}-DOMAIN] Quét định kỳ thành công: Bảng giá ổn định (không có biến động). Bỏ qua gửi báo cáo để tránh spam.")

if __name__ == "__main__":
    provider = MatBaoDomainProvider()
    provider.run()
