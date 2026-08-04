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

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.base_provider import BaseProvider
from core.diff_engine import DiffEngine
from core.telegram_notifier import TelegramNotifier
from core.retry_handler import retry, get_random_user_agent, random_delay


class LongVanDomainProvider(BaseProvider):
    """
    Crawler chuyên biệt cho Sản Phẩm Tên Miền Long Vân (longvan.net).
    Long Vân là nhà cung cấp BENCHMARK (chuẩn) dùng để so sánh với đối thủ.
    Bóc tách: TLD, Phí Đăng Ký, Phí Gia Hạn, Phí Chuyển Đổi.
    """
    def __init__(self):
        super().__init__(
            provider_name="longvan",
            base_url="https://longvan.net/domain#bang-gia-ten-mien"
        )
        self.diff_engine = DiffEngine()
        self.telegram = TelegramNotifier()

    @retry(max_attempts=3, backoff_factor=2.0)
    def scrape_domain_pricing_bs4(self) -> list:
        """
        Bóc tách nhanh qua HTTP Requests + BeautifulSoup (fallback).
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
                rows = soup.select("table tr, .price-table tr, .table-domain tr, .bang-gia tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    if len(cols) >= 2:
                        col_texts = [col.get_text(strip=True) for col in cols]
                        tld_text = col_texts[0]
                        tld_match = re.search(r'(\.[a-zA-Z\.]+)', tld_text)
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
        screenshot_path = os.path.join(screenshot_dir, f"longvan_domain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        with sync_playwright() as p:
            browser, context, page = self.launch_browser(p)
            try:
                page.goto(self.base_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(3000, 5000))

                # Tắt các banner / modal quảng cáo đè màn hình trước khi chụp ảnh
                try:
                    page.evaluate("""
                        document.querySelectorAll('.modal, .popup, [class*="popup"], [id*="popup"], [class*="modal"], [class*="banner"], [id*="banner"], .fancybox-overlay, .fade').forEach(e => e.remove());
                        document.body.classList.remove('modal-open');
                    """)
                    page.wait_for_timeout(500)
                except Exception:
                    pass

                # Cuộn xuống khu vực bảng giá nếu cần
                try:
                    page.evaluate("document.querySelector('#bang-gia-ten-mien, table')?.scrollIntoView()")
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Chụp screenshot
                try:
                    page.screenshot(path=screenshot_path, full_page=False)
                    print(f"📸 Đã chụp ảnh màn hình giao diện: {screenshot_path}")
                except Exception as e_ss:
                    print(f"⚠️ Không thể chụp screenshot: {e_ss}")

                rows = page.query_selector_all("table tr, .table-price tr, .domain-price-row, .bang-gia tr")
                for r in rows:
                    cols = r.query_selector_all("td, th")
                    if len(cols) >= 2:
                        col_texts = [col.inner_text().strip() for col in cols]
                        tld_text = col_texts[0]
                        tld_match = re.search(r'(\.[a-zA-Z\.]+)', tld_text)
                        if tld_match:
                            tld = tld_match.group(1).lower()
                            # 6 columns structure:
                            # 0: TLD, 1: Lệ phí ĐK, 2: Phí duy trì, 3: Phí DV năm 1, 4: Phí DV năm 2+, 5: Tổng năm 1, 6: Tổng năm 2+
                            if len(col_texts) >= 7:
                                reg_price = self.clean_price(col_texts[5])
                                renew_price = self.clean_price(col_texts[6])
                            elif len(col_texts) >= 6:
                                reg_price = self.clean_price(col_texts[5])
                                renew_price = self.clean_price(col_texts[1]) + self.clean_price(col_texts[2])
                            else:
                                reg_price = self.clean_price(col_texts[1])
                                renew_price = self.clean_price(col_texts[2]) if len(col_texts) > 2 else reg_price

                            transfer_price = None  # Long Van website does not list transfer price in table
                            promo = f"KM: Phí DV 0đ" if "0 đ" in (col_texts[3] if len(col_texts) > 3 else "") else ""

                            if reg_price > 0 or renew_price > 0:
                                items.append({
                                    "tld": tld,
                                    "register_price": reg_price,
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
        Hybrid: Playwright trước, HTTP/BS4 fallback.
        """
        items = []
        screenshot_path = ""

        try:
            items, screenshot_path = self.scrape_domain_pricing_playwright()
        except Exception as e:
            print(f"⚠️ Lỗi Playwright ({e}), chuyển sang dùng HTTP/BS4...")

        if not items:
            items = self.scrape_domain_pricing_bs4()

        # Deduplicate
        unique_items = {}
        for it in items:
            tld = it["tld"]
            if tld not in unique_items or (it["register_price"] > 0 and unique_items[tld]["register_price"] == 0):
                unique_items[tld] = it

        final_list = list(unique_items.values())
        print(f"✅ [{self.provider_name.upper()}-DOMAIN] Đã thu thập {len(final_list)} đuôi tên miền.")
        return final_list, screenshot_path

    def run(self):
        """
        Luồng chính: Scrape -> Lưu snapshot Long Vân (Benchmark) -> Telegram Report
        """
        domain_items, screenshot_path = self.scrape_domain_pricing()

        if not domain_items:
            print(f"⚠️ [{self.provider_name.upper()}-DOMAIN] Không lấy được dữ liệu tên miền nào.")
            return

        # Lưu snapshot Long Vân (làm benchmark cho các đối thủ khác)
        self.diff_engine.save_longvan_snapshot(domain_items, "domain", url=self.base_url)

        # Báo cáo Telegram
        report_msg = (
            f"🏠 *[MARKET-AI] CẬP NHẬT BẢNG GIÁ BENCHMARK - LONG VÂN (TÊN MIỀN)*\n"
            f"⏰ *Thời gian:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"🌐 *Nguồn:* {self.base_url}\n"
            f"📊 *Tổng số TLD:* {len(domain_items)} đuôi tên miền\n"
            f"{'⎯' * 20}\n"
        )
        for item in domain_items[:10]:
            report_msg += f"  • `{item['tld']}` — ĐK: `{item['register_price']:,.0f}đ` | GH: `{item['renew_price']:,.0f}đ`\n"
        if len(domain_items) > 10:
            report_msg += f"  ... và {len(domain_items) - 10} TLD khác\n"
        report_msg += f"\n🤖 _Market AI Engine - Benchmark Long Vân đã cập nhật_"

        print("\n--- NỘI DUNG BÁO CÁO TELEGRAM ---")
        print(report_msg)
        print("---------------------------------\n")

        if self.telegram.is_configured():
            self.telegram.send_message(report_msg)
            if screenshot_path and os.path.exists(screenshot_path):
                self.telegram.send_photo(screenshot_path, caption="📸 Screenshot bảng giá tên miền Long Vân (Benchmark)")


if __name__ == "__main__":
    provider = LongVanDomainProvider()
    provider.run()
