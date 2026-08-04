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


class PaVietnamDomainProvider(BaseProvider):
    """
    Crawler chuyên biệt cho Sản Phẩm Tên Miền PA Việt Nam (pavietnam.vn).
    Bóc tách: TLD, Phí Đăng Ký, Phí Gia Hạn, Phí Chuyển Đổi.
    """
    def __init__(self):
        super().__init__(
            provider_name="pavietnam",
            base_url="https://www.pavietnam.vn/vn/ten-mien-bang-gia.html"
        )
        self.diff_engine = DiffEngine()
        self.telegram = TelegramNotifier()

    @retry(max_attempts=3, backoff_factor=2.0)
    def scrape_domain_pricing_bs4(self) -> list:
        """
        Bóc tách nhanh qua HTTP Requests + BeautifulSoup (fallback).
        PA Việt Nam HTML structure:
          <td class="dang-ky-moi">
            <span class="old">700.000đ</span>    <!-- Giá gốc gạch ngang -->
            <strong>450.000<sup>đ</sup></strong>  <!-- Giá KM thực tế -->
          </td>
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
                rows = soup.select("table tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    if len(cols) < 2:
                        continue

                    # Cột 0: TLD — PA dùng <span id="vn">.vn</span>
                    tld_col = cols[0]
                    tld_spans = tld_col.find_all('span', id=True)
                    if tld_spans:
                        # Lấy TLD từ span (ví dụ: <span id="vn">.vn</span>)
                        tld = '.' + tld_spans[0]['id'].lower()
                    else:
                        tld_text = tld_col.get_text(strip=True)
                        tld_match = re.match(r'(\.[a-z\.]+)', tld_text.lower())
                        if not tld_match:
                            continue
                        tld = tld_match.group(1)

                    # Cột 1: Giá Đăng Ký (có thể có giá gạch ngang + giá KM)
                    reg_col = cols[1]
                    old_span = reg_col.find('span', class_='old')
                    strong_tag = reg_col.find('strong')

                    if strong_tag:
                        # Có giá KM → lấy giá KM làm giá thực tế
                        reg_price = self.clean_price(strong_tag.get_text(strip=True))
                        reg_price_original = self.clean_price(old_span.get_text(strip=True)) if old_span else None
                    else:
                        # Không có KM → lấy text bình thường
                        reg_price = self.clean_price(reg_col.get_text(strip=True).split('\n')[0])
                        reg_price_original = None

                    # Cột 2: Giá Gia Hạn
                    # PA Việt Nam ẩn tổng chi phí gia hạn trong tooltip (div.iquestion_tooltip)
                    # Cấu trúc: <td class="gia-han"> 150.000 <sup>đ</sup>
                    #   <div class="iquestion_tooltip">
                    #     <div class="item_price">Phí duy trì: 350.000đ</div>
                    #     <div class="item_price">DV quản trị: 150.000đ</div>
                    #     <div class="item_price">Thuế GTGT: 12.000đ</div>
                    #     <div class="item_price">Tổng: 512.000đ</div> ← LẤY GIÁ NÀY
                    renew_price = 0.0
                    renew_price_display = 0.0  # Giá hiển thị trên cột (phần nhỏ)
                    if len(cols) > 2:
                        renew_col = cols[2]
                        # Tìm giá "Tổng" trong tooltip
                        tooltip = renew_col.find('div', class_='iquestion_tooltip')
                        if tooltip:
                            # Lấy tất cả item_fr (chứa giá trị) — giá trị cuối cùng là "Tổng"
                            item_frs = tooltip.find_all('div', class_='item_fr')
                            if item_frs:
                                total_text = item_frs[-1].get_text(strip=True)
                                renew_price = self.clean_price(total_text)
                            # Lấy giá hiển thị trên cột (text trước tooltip)
                            renew_texts = renew_col.find_all(string=True, recursive=False)
                            renew_raw = ''.join([t.strip() for t in renew_texts if t.strip()])
                            renew_price_display = self.clean_price(renew_raw) if renew_raw else 0.0
                        else:
                            # Không có tooltip → lấy text bình thường
                            renew_strong = renew_col.find('strong')
                            if renew_strong:
                                renew_price = self.clean_price(renew_strong.get_text(strip=True))
                            else:
                                renew_texts = renew_col.find_all(string=True, recursive=False)
                                renew_raw = ''.join([t.strip() for t in renew_texts if t.strip()])
                                renew_price = self.clean_price(renew_raw) if renew_raw else 0.0

                    # Cột 3: Giá Chuyển Đổi (nếu có)
                    transfer_price = 0.0
                    if len(cols) > 3:
                        transfer_price = self.clean_price(cols[3].get_text(strip=True))

                    if reg_price > 0 or renew_price > 0:
                        item = {
                            "tld": tld,
                            "register_price": reg_price,
                            "renew_price": renew_price,
                            "transfer_price": transfer_price,
                            "promo_note": ""
                        }
                        if reg_price_original and reg_price_original != reg_price:
                            item["register_price_original"] = reg_price_original
                        items.append(item)
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
        screenshot_path = os.path.join(screenshot_dir, f"pavietnam_domain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        with sync_playwright() as p:
            browser, context, page = self.launch_browser(p)
            try:
                page.goto(self.base_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(random.randint(3000, 5000))

                # Chụp screenshot
                try:
                    page.screenshot(path=screenshot_path, full_page=False)
                    print(f"📸 Đã chụp ảnh màn hình giao diện: {screenshot_path}")
                except Exception as e_ss:
                    print(f"⚠️ Không thể chụp screenshot: {e_ss}")

                rows = page.query_selector_all("table tr")
                for r in rows:
                    cols = r.query_selector_all("td, th")
                    if len(cols) < 2:
                        continue

                    # Cột 0: TLD — PA dùng <span id="vn">.vn</span>
                    tld_spans = cols[0].evaluate("""el => {
                        const spans = el.querySelectorAll('span[id]');
                        return spans.length > 0 ? '.' + spans[0].id.toLowerCase() : null;
                    }""")
                    if tld_spans:
                        tld = tld_spans
                    else:
                        tld_text = cols[0].inner_text().strip()
                        tld_match = re.match(r'(\.[a-z\.]+)', tld_text.lower())
                        if not tld_match:
                            continue
                        tld = tld_match.group(1)

                    # Cột 1: Giá Đăng Ký — bóc tách giá gạch ngang vs giá KM qua JS DOM
                    reg_data = cols[1].evaluate("""el => {
                        const oldSpan = el.querySelector('span.old');
                        const strongTag = el.querySelector('strong');
                        return {
                            old_price: oldSpan ? oldSpan.innerText.trim() : null,
                            promo_price: strongTag ? strongTag.innerText.trim() : null,
                            full_text: el.innerText.trim().split('\\n')[0]
                        };
                    }""")

                    if reg_data.get("promo_price"):
                        reg_price = self.clean_price(reg_data["promo_price"])
                        reg_price_original = self.clean_price(reg_data["old_price"]) if reg_data.get("old_price") else None
                    else:
                        reg_price = self.clean_price(reg_data.get("full_text", ""))
                        reg_price_original = None

                    # Cột 2: Giá Gia Hạn — lấy "Tổng" từ tooltip ẩn (Tooltipster plugin)
                    renew_price = 0.0
                    if len(cols) > 2:
                        renew_data = cols[2].evaluate("""el => {
                            // Cấu trúc PA Việt Nam dùng Tooltipster làm sạch innerHTML sau khi init.
                            // Cần lấy content qua $(ttEl).tooltipster('content') hoặc innerHTML trước khi init.
                            const ttEl = el.querySelector('.iquestion_tooltip, [class*="tooltip"]');
                            if (ttEl && typeof $ !== 'undefined') {
                                try {
                                    let cnt = $(ttEl).tooltipster('content');
                                    if (cnt) {
                                        let text = '';
                                        if (typeof cnt === 'string') text = cnt;
                                        else if (cnt.jquery || cnt instanceof HTMLElement) text = $(cnt).text();
                                        else if (cnt[0]) text = $(cnt[0]).text();

                                        // Parse dòng 'Tổng:'
                                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                                        for (let i = 0; i < lines.length; i++) {
                                            if (lines[i].includes('Tổng') && i + 1 < lines.length) {
                                                return { total: lines[i+1], display: null };
                                            }
                                        }
                                        // Hoặc lấy chuỗi sau chữ 'Tổng:'
                                        const totalMatch = text.match(/Tổng\\s*:\\s*([\\d\\.\\,]+\\s*đ?)/i);
                                        if (totalMatch) return { total: totalMatch[1], display: null };
                                    }
                                } catch(e) {}
                            }

                            // Fallback: nếu Tooltipster chưa init hoặc không có
                            const tooltip = el.querySelector('.iquestion_tooltip');
                            if (tooltip) {
                                const itemFrs = tooltip.querySelectorAll('.item_fr');
                                if (itemFrs.length > 0) {
                                    return { total: itemFrs[itemFrs.length - 1].innerText.trim(), display: null };
                                }
                            }

                            const strongTag = el.querySelector('strong');
                            if (strongTag) return { total: strongTag.innerText.trim(), display: null };
                            let text = '';
                            for (const node of el.childNodes) {
                                if (node.nodeType === 3) text += node.textContent.trim();
                            }
                            return { total: text, display: null };
                        }""")
                        if renew_data and isinstance(renew_data, dict):
                            renew_price = self.clean_price(renew_data.get("total", "")) if renew_data.get("total") else 0.0
                        elif renew_data:
                            renew_price = self.clean_price(str(renew_data))

                    # Cột 3: Giá Chuyển Đổi
                    transfer_price = 0.0
                    if len(cols) > 3:
                        transfer_price = self.clean_price(cols[3].inner_text().strip())

                    if reg_price > 0 or renew_price > 0:
                        item = {
                            "tld": tld,
                            "register_price": reg_price,
                            "renew_price": renew_price,
                            "transfer_price": transfer_price,
                            "promo_note": ""
                        }
                        if reg_price_original and reg_price_original != reg_price:
                            item["register_price_original"] = reg_price_original
                        items.append(item)
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

    def run(self, force_notify: bool = False):
        """
        Luồng chính: Scrape -> Diff -> Save -> Smart Notification (Email & Telegram)
        Chỉ chủ động gửi báo cáo khi (1) Có biến động giá/TLD mới HOẶC (2) Lịch 8h00 / Ép buộc gửi (force_notify=True).
        """
        domain_items, screenshot_path = self.scrape_domain_pricing()

        if not domain_items:
            print(f"⚠️ [{self.provider_name.upper()}-DOMAIN] Không lấy được dữ liệu tên miền nào.")
            return

        # So sánh biến động với snapshot trước (3-way với Long Vân)
        diff_res = self.diff_engine.compare_domain_data("pavietnam_domain", domain_items, url=self.base_url)

        has_changes = diff_res.get("has_changes", False)
        should_notify = force_notify or has_changes

        report_msg = self.telegram.format_domain_diff_report("PA Việt Nam (Tên miền)", diff_res)

        if should_notify:
            print(f"\n🔔 [{self.provider_name.upper()}-DOMAIN] {'[CẢNH BÁO BIẾN ĐỘNG]' if has_changes else '[GỬI BÁO CÁO THỦ CÔNG/ĐỊNH KỲ]'} -> Đang gửi báo cáo...")
            print("--- NỘI DUNG BÁO CÁO TELEGRAM ---")
            print(report_msg)
            print("---------------------------------\n")

            if self.telegram.is_configured():
                self.telegram.send_message(report_msg)
                if screenshot_path and os.path.exists(screenshot_path):
                    self.telegram.send_photo(screenshot_path, caption="📸 Screenshot giao diện PA Việt Nam Tên miền hiện tại")

            # Gửi báo cáo Email
            try:
                from core.email_notifier import EmailNotifier
                email = EmailNotifier()
                if email.is_configured():
                    html_body = email.format_domain_report_html("PA VIỆT NAM", diff_res)
                    email.send_report(
                        subject=f"[Market AI] {'🚨 [CẢNH BÁO] Biến Động Giá' if has_changes else '📊 Báo Cáo Cạnh Tranh'} - PA VIỆT NAM - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                        html_body=html_body,
                        screenshot_paths=[screenshot_path] if (screenshot_path and os.path.exists(screenshot_path)) else []
                    )
            except Exception as e:
                print(f"⚠️ Lỗi gửi email PA Việt Nam: {e}")
        else:
            print(f"ℹ️ [{self.provider_name.upper()}-DOMAIN] Quét định kỳ thành công: Bảng giá ổn định (không có biến động). Bỏ qua gửi báo cáo để tránh spam.")


if __name__ == "__main__":
    provider = PaVietnamDomainProvider()
    provider.run()
