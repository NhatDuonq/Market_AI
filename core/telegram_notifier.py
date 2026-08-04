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
        Gửi tin nhắn văn bản đến Telegram Chat.
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
                print(f"[TelegramNotifier] ❌ Gửi tin nhắn thất bại ({res.status_code}): {res.text}")
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
        Định dạng dữ liệu biến động sản phẩm Tên miền thành Telegram Markdown.
        Bao gồm: Giá cũ, Giá mới, Mức chênh lệch, So sánh vs Long Vân, TLD Availability.
        """
        lines = []
        if is_demo:
            lines.append("⚠️ *[BẢN TIN GIẢ LẬP DEMO - KHÔNG PHẢI DỮ LIỆU THỰC]*")

        clean_pname = provider_name.split("(")[0].strip().upper()
        lines.append(f"🚨 *[MARKET-AI] BÁO CÁO BIẾN ĐỘNG GIÁ & ĐỐI SO - {clean_pname} (TÊN MIỀN)*")
        lines.append(f"⏰ *Thời gian quét:* `{changes.get('timestamp', '')}`")
        lines.append(f"🌐 *Nguồn dữ liệu:* {changes.get('url', '')}")
        lines.append("⎯" * 20)

        price_changes = changes.get("price_changes", [])
        new_items = changes.get("new_tlds", [])
        lv_summary = changes.get("longvan_summary", {})
        cheaper_items = lv_summary.get("cheaper_items", [])
        expensive_items = lv_summary.get("expensive_items", [])
        tld_availability = changes.get("tld_availability", {})

        if new_items:
            lines.append(f"✨ *PHÁT HIỆN {len(new_items)} TLD MỚI RA MẮT:*")
            for item in new_items[:10]:
                tld = item.get('tld', 'N/A')
                reg_p = item.get('register_price', 0)
                ren_p = item.get('renew_price', 0)
                lv_reg = item.get('longvan_register_price', 0)

                lines.append(f" 🆕 *{tld}*")
                lines.append(f"    ├─ Đăng ký: `{reg_p:,.0f}đ`")
                if ren_p > 0:
                    lines.append(f"    ├─ Gia hạn: `{ren_p:,.0f}đ`")
                if lv_reg > 0:
                    gap = reg_p - lv_reg
                    badge = "⚠️ *ĐỐI THỦ GIÁ THẤP HƠN*" if gap < 0 else "✅ *LONG VÂN GIÁ THẤP HƠN*" if gap > 0 else "⚖️ *BẰNG GIÁ*"
                    lines.append(f"    └─ Giá Long Vân: `{lv_reg:,.0f}đ` ({badge})")
            lines.append("")

        if price_changes:
            lines.append(f"📈📉 *CHI TIẾT {len(price_changes)} ĐỢT BIẾN ĐỘNG GIÁ:*")
            for item in price_changes[:6]:
                item_name = item.get("tld", "Gói")
                old_p = item.get("old_price", 0)
                new_p = item.get("new_price", 0)
                lv_p = item.get("longvan_price", 0)
                field = item.get("field", "Giá đăng ký năm đầu")
                diff = new_p - old_p
                pct = (diff / old_p * 100) if old_p > 0 else 0

                badge = "🔥 *GIẢM GIÁ*" if diff < 0 else "🔺 *TĂNG GIÁ*"
                arrow = "🔻" if diff < 0 else "🔺"

                lines.append(f" {badge} - *{item_name}* (`{field}`)")
                lines.append(f"    ├─ Giá cũ: `{old_p:,.0f}đ`")
                lines.append(f"    ├─ Giá mới: *`{new_p:,.0f}đ`*")
                lines.append(f"    ├─ Chênh lệch: {arrow} *`{abs(diff):,.0f}đ`* ({pct:+.1f}%)")
                if lv_p > 0:
                    lv_gap = new_p - lv_p
                    lv_tag = "⚠️ *ĐỐI THỦ GIÁ THẤP HƠN*" if lv_gap < 0 else "✅ *LONG VÂN GIÁ THẤP HƠN*" if lv_gap > 0 else "⚖️ *BẰNG GIÁ*"
                    lines.append(f"    └─ Giá LV: `{lv_p:,.0f}đ` → Chênh: *`{abs(lv_gap):,.0f}đ`* ({lv_tag})")
            if len(price_changes) > 6:
                lines.append(f"  ... và {len(price_changes) - 6} đợt biến động giá khác\n")
            else:
                lines.append("")

        # TLD Availability Summary
        if tld_availability:
            lv_exclusive = tld_availability.get("longvan_exclusive", [])
            comp_exclusive = tld_availability.get("competitor_exclusive", [])
            if lv_exclusive or comp_exclusive:
                lines.append("🔍 *ĐỘ PHỦ TLD (TLD AVAILABILITY):*")
                if lv_exclusive:
                    lv_str = ', '.join(lv_exclusive[:10]) + (f' (+{len(lv_exclusive)-10} TLD khác)' if len(lv_exclusive) > 10 else '')
                    lines.append(f" ✅ Long Vân có, đối thủ KHÔNG: `{lv_str}`")
                if comp_exclusive:
                    comp_str = ', '.join(comp_exclusive[:10]) + (f' (+{len(comp_exclusive)-10} TLD khác)' if len(comp_exclusive) > 10 else '')
                    lines.append(f" ⚠️ Đối thủ có, Long Vân KHÔNG: `{comp_str}`")
                lines.append("")

        if lv_summary:
            total_tlds = lv_summary.get("total_tlds_compared", 0)
            reg_cheap = lv_summary.get("reg_cheaper_count", 0)
            reg_exp = lv_summary.get("reg_expensive_count", 0)
            reg_eq = lv_summary.get("reg_equal_count", 0)

            renew_cheap = lv_summary.get("renew_cheaper_count", 0)
            renew_exp = lv_summary.get("renew_expensive_count", 0)
            renew_eq = lv_summary.get("renew_equal_count", 0)

            twoyr_cheap = lv_summary.get("twoyr_cheaper_count", 0)
            twoyr_exp = lv_summary.get("twoyr_expensive_count", 0)
            twoyr_eq = lv_summary.get("twoyr_equal_count", 0)

            if total_tlds > 0:
                lines.append(f"⚔️ *TỔNG QUAN VỊ THẾ GIÁ VS LONG VÂN (So sánh cùng TLD trên {total_tlds} đuôi tên miền):*")
                lines.append(f" 📌 *Giá Đăng Ký Năm 1:*")
                lines.append(f"    ├─ Đối thủ giá thấp hơn: *{reg_cheap}* TLD ⚠️")
                lines.append(f"    ├─ Long Vân & Đối thủ BẰNG GIÁ: *{reg_eq}* TLD ⚖️")
                lines.append(f"    └─ Long Vân giá thấp hơn: *{reg_exp}* TLD ✅")
                lines.append(f" 📌 *Giá Gia Hạn Hàng Năm (Từ năm 2):*")
                lines.append(f"    ├─ Đối thủ giá thấp hơn: *{renew_cheap}* TLD ⚠️")
                lines.append(f"    ├─ Long Vân & Đối thủ BẰNG GIÁ: *{renew_eq}* TLD ⚖️")
                lines.append(f"    └─ Long Vân giá thấp hơn: *{renew_exp}* TLD ✅")
                lines.append(f" 📌 *Tổng Chi Phí 2 Năm (Năm 1 + Gia hạn):*")
                lines.append(f"    ├─ Đối thủ giá thấp hơn: *{twoyr_cheap}* TLD ⚠️")
                lines.append(f"    ├─ Long Vân & Đối thủ BẰNG GIÁ: *{twoyr_eq}* TLD ⚖️")
                lines.append(f"    └─ Long Vân giá thấp hơn: *{twoyr_exp}* TLD ✅")
                lines.append("")

        try:
            from core.ai_analyzer import AIAnalyzer
            ai = AIAnalyzer()
            ai_summary = ai.analyze_market_changes(provider_name, product_type, changes)
            lines.append("🧠 *PHÂN TÍCH & ĐỀ XUẤT TỪ MARKET AI (DÀNH CHO LONG VÂN):*")
            lines.append(ai_summary)
            lines.append("")
        except Exception as e_ai:
            print(f"[TelegramNotifier] ⚠️ Lỗi AI Analysis: {e_ai}")

        lines.append("⎯" * 20)
        lines.append("🤖 _Hệ thống Market AI Engine theo dõi tự động 24/7_")
        return "\n".join(lines)
