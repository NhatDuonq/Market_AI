import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


class TelegramNotifier:
    """
    Module gửi thông báo biến động giá, TLD mới và hình ảnh thay đổi giao diện qua Telegram Bot.
    """
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Gửi tin nhắn văn bản đến Telegram Chat (tự động fallback nếu Markdown lỗi syntax).
        """
        if not self.is_configured():
            print(f"[TelegramNotifier] ⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. Nguồn tin nhắn:\n{text}")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                print("[TelegramNotifier] ✅ Đã gửi tin nhắn Telegram thành công.")
                return True
            else:
                print(f"[TelegramNotifier] ⚠️ Gửi với parse_mode={parse_mode} thất bại ({res.status_code}): {res.text}. Thử lại gửi Plain Text...")
                payload.pop("parse_mode", None)
                res_fallback = requests.post(url, json=payload, timeout=10)
                if res_fallback.status_code == 200:
                    print("[TelegramNotifier] ✅ Đã gửi tin nhắn Telegram (Plain Text Fallback) thành công.")
                    return True
                else:
                    print(f"[TelegramNotifier] ❌ Gửi tin nhắn thất bại ({res_fallback.status_code}): {res_fallback.text}")
                    return False
        except Exception as e:
            print(f"[TelegramNotifier] ❌ Lỗi kết nối Telegram API: {e}")
            return False

    def send_photo(self, photo_path: str, caption: str = None) -> bool:
        """
        Gửi hình ảnh (screenshot giao diện) đến Telegram Chat.
        """
        if not self.is_configured():
            print(f"[TelegramNotifier] ⚠️ Chưa cấu hình Telegram. Không thể gửi ảnh: {photo_path}")
            return False

        if not os.path.exists(photo_path):
            print(f"[TelegramNotifier] ❌ Không tìm thấy file ảnh: {photo_path}")
            return False

        url = f"{self.base_url}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo_file:
                files = {'photo': photo_file}
                data = {'chat_id': self.chat_id}
                if caption:
                    data['caption'] = caption
                    data['parse_mode'] = 'Markdown'

                res = requests.post(url, data=data, files=files, timeout=30)
                if res.status_code == 200:
                    print("[TelegramNotifier] ✅ Đã gửi ảnh Telegram thành công.")
                    return True
                else:
                    print(f"[TelegramNotifier] ❌ Gửi ảnh thất bại ({res.status_code}): {res.text}")
                    return False
        except Exception as e:
            print(f"[TelegramNotifier] ❌ Lỗi gửi ảnh Telegram: {e}")
            return False

    def send_report_with_photo(self, report_msg: str, photo_path: str = None, caption: str = None) -> bool:
        """
        Gửi cả báo cáo dạng chữ và ảnh chụp giao diện đính kèm qua Telegram.
        """
        msg_sent = self.send_message(report_msg)

        if not photo_path:
            import glob
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screenshots = glob.glob(os.path.join(project_root, "storage", "screenshots", "*.png"))
            if screenshots:
                photo_path = max(screenshots, key=os.path.getctime)

        if photo_path and os.path.exists(photo_path):
            cap = caption or "📸 Screenshot Giao diện / Bảng giá mới nhất"
            self.send_photo(photo_path, caption=cap)

        return msg_sent

    def format_domain_diff_report(self, provider_name: str, changes: dict, is_demo: bool = False) -> str:
        return self.format_diff_report(provider_name, "domain", changes, is_demo)

    def format_diff_report(self, provider_name: str, product_type: str, changes: dict, is_demo: bool = False) -> str:
        """
        Định dạng dữ liệu biến động sản phẩm Tên miền thành Telegram Markdown ngắn gọn, súc tích, đầy đủ thông tin chìa khóa.
        """
        lines = []
        clean_pname = provider_name.split("(")[0].strip().upper()
        dashboard_url = os.getenv("DASHBOARD_URL", "https://thitruong.longvan.net")

        if is_demo:
            lines.append("⚠️ *[BẢN TIN GIẢ LẬP DEMO]*")

        lines.append(f"🚨 *[MARKET-AI] BÁO CÁO CẠNH TRANH - {clean_pname} (TÊN MIỀN)*")
        lines.append(f"⏰ *Thời gian:* `{changes.get('timestamp', '')}`")
        lines.append(f"🌐 *Nguồn:* {changes.get('url', '')}")
        lines.append("⎯" * 20)

        price_changes = changes.get("price_changes", [])
        new_items = changes.get("new_tlds", [])
        lv_summary = changes.get("longvan_summary", {})
        tld_availability = changes.get("tld_availability", {})

        # 1. BIẾN ĐỘNG GIÁ
        if price_changes:
            lines.append(f"📈📉 *PHÁT HIỆN {len(price_changes)} ĐỢT BIẾN ĐỘNG GIÁ:*")
            for item in price_changes[:5]:
                item_name = item.get("tld", "")
                field = item.get("field", "")
                old_p = item.get("old_price", 0)
                new_p = item.get("new_price", 0)
                arrow = "🔻" if new_p < old_p else "🔺"
                lines.append(f"  {arrow} *{item_name}* (`{field}`): `{old_p:,.0f}đ` ➔ *`{new_p:,.0f}đ`*")
            if len(price_changes) > 5:
                lines.append(f"  ... và {len(price_changes) - 5} TLD đổi giá khác.")
        else:
            lines.append("📈 *BIẾN ĐỘNG GIÁ:* ✅ Bảng giá niêm yết giữ nguyên ổn định.")

        lines.append("")

        # 2. TLD MỚI RA MẮT
        if new_items:
            lines.append(f"✨ *PHÁT HIỆN {len(new_items)} TLD MỚI RA MẮT:*")
            for item in new_items[:5]:
                tld = item.get('tld', 'N/A')
                reg_p = item.get('register_price', 0)
                lines.append(f"  🆕 *{tld}*: Giá ĐK `{reg_p:,.0f}đ`")
        else:
            lines.append("🆕 *TLD MỚI:* ✅ Không phát hiện TLD mới ra mắt.")

        lines.append("")

        # 3. VỊ THẾ VS LONG VÂN (CHI TIẾT MỤC TIÊU CỤ THỂ)
        if lv_summary:
            total_tlds = lv_summary.get("total_tlds_compared", 0)
            twoyr_cheap = lv_summary.get("twoyr_cheaper_count", 0)
            twoyr_exp = lv_summary.get("twoyr_expensive_count", 0)
            twoyr_eq = lv_summary.get("twoyr_equal_count", 0)

            cheaper_items = lv_summary.get("cheaper_items", [])
            expensive_items = lv_summary.get("expensive_items", [])

            cheap_tlds = list(set(c.get("tld") for c in cheaper_items if c.get("tld") and c.get("field") == "Tổng chi phí 2 năm"))
            exp_tlds = list(set(e.get("tld") for e in expensive_items if e.get("tld") and e.get("field") == "Tổng chi phí 2 năm"))

            lines.append(f"⚔️ *VỊ THẾ GIÁ 2 NĂM VS LONG VÂN ({total_tlds} TLD):*")
            if exp_tlds:
                exp_str = ", ".join(exp_tlds[:6]) + (f" (+{len(exp_tlds)-6})" if len(exp_tlds) > 6 else "")
                lines.append(f"  ✅ *Long Vân giá tốt hơn ({twoyr_exp} TLD):* `{exp_str}`")
            if cheap_tlds:
                cheap_str = ", ".join(cheap_tlds[:6]) + (f" (+{len(cheap_tlds)-6})" if len(cheap_tlds) > 6 else "")
                lines.append(f"  ⚠️ *Đối thủ giá thấp hơn ({twoyr_cheap} TLD):* `{cheap_str}`")
            if twoyr_eq > 0:
                lines.append(f"  ⚖️ *Bằng giá hai bên:* `{twoyr_eq} TLD`")

        lines.append("")

        # 4. ĐỘ PHỦ TLD MỞ RỘNG
        if tld_availability:
            comp_exclusive = tld_availability.get("competitor_exclusive", [])
            if comp_exclusive:
                lines.append(f"🏷️ *THỊ PHẦN ĐỐI THỦ CÓ (LV chưa có {len(comp_exclusive)} TLD):*\n  `{', '.join(comp_exclusive[:8])}` (vẫn còn {len(comp_exclusive)-8} TLD khác)")
                lines.append("")

        lines.append("⎯" * 20)
        lines.append(f"🔗 *XEM ĐẦY ĐỦ BẢNG GIÁ & AI PHÂN TÍCH TẠI DASHBOARD:*\n🌐 {dashboard_url}")
        return "\n".join(lines)
