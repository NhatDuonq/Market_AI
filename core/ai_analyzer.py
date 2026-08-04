import os
import json
import hashlib
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Cấu hình Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "ai_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


class AIAnalyzer:
    """
    Module phân tích chiến lược biến động giá và đưa ra đề xuất đối ứng bằng Gemini AI.
    - Hỗ trợ Caching kết quả dựa trên MD5 hash của dữ liệu đầu vào.
    - Hỗ trợ Structured Output (JSON) từ Gemini API.
    - Phân tích TLD Availability, Tổng chi phí 2 năm, và Giá chuyển đổi.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "YOUR_GEMINI_API_KEY")

    def _get_cache_path(self, data_hash: str) -> str:
        return os.path.join(CACHE_DIR, f"{data_hash}.json")

    def _generate_data_hash(self, data: dict) -> str:
        hash_data = {k: v for k, v in data.items() if k not in ["timestamp", "url"]}
        data_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(data_str.encode('utf-8')).hexdigest()

    def analyze_domain_changes(self, provider_name: str, changes: dict) -> str:
        return self.analyze_market_changes(provider_name, "domain", changes)

    def analyze_market_changes(self, provider_name: str, product_type: str, changes: dict) -> str:
        prod_title = "Tên miền"
        price_changes = changes.get("price_changes", [])
        new_items = changes.get("new_tlds", [])
        lv_summary = changes.get("longvan_summary", {})
        cheaper_items = lv_summary.get("cheaper_items", [])
        expensive_items = lv_summary.get("expensive_items", [])
        tld_availability = changes.get("tld_availability", {})

        # Nếu không có price_changes và new_items, vẫn thực hiện phân tích đầy đủ dựa trên Vị Thế Cạnh Tranh & TLD Availability
        if not price_changes and not new_items:
            return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability)

        # 1. Kiểm tra Cache
        data_hash = self._generate_data_hash(changes)
        cache_path = self._get_cache_path(data_hash)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_res = json.load(f)
                logger.info(f"AI Cache Hit: {data_hash}")
                return self._format_ai_response(cached_res, provider_name, prod_title)
            except Exception as e:
                logger.warning(f"Failed to read cache {data_hash}: {e}")

        # 2. Gọi API hoặc fallback
        if not self.is_configured():
            logger.info("Gemini API Key missing, falling back to rule-based AI")
            return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability)

        # Build prompt với dữ liệu mở rộng
        tld_avail_summary = ""
        if tld_availability:
            lv_exclusive = tld_availability.get("longvan_exclusive", [])
            comp_exclusive = tld_availability.get("competitor_exclusive", [])
            tld_avail_summary = f"""
4. Phân tích Độ Phủ TLD:
- TLD chỉ Long Vân bán (lợi thế ngách): {json.dumps(lv_exclusive, ensure_ascii=False)}
- TLD chỉ đối thủ bán (Long Vân bỏ lỡ): {json.dumps(comp_exclusive, ensure_ascii=False)}
"""

        # Lọc ra các mục so sánh Tổng chi phí 2 năm
        comparison_2yr = [c for c in changes.get("longvan_comparison", []) if c.get("field") == "Tổng chi phí 2 năm"]

        prompt = f"""
Bạn là Giám đốc Chiến lược Giá & Thị Phần (Chief Pricing Officer) của LONG VÂN CLOUD SOLUTION tại Việt Nam.
Bạn đang đối soát chiến lược giá tên miền trực tiếp với đối thủ: {provider_name.upper()}.

DỮ LIỆU ĐỐI SOÁT CHI TIẾT:
1. Biến động giá mới phát hiện của đối thủ ({provider_name}):
{json.dumps(price_changes[:10], ensure_ascii=False, indent=2)}

2. TLD mới đối thủ mới ra mắt:
{json.dumps(new_items[:10], ensure_ascii=False, indent=2)}

3. Vị thế giá (Long Vân vs {provider_name}):
- TLD đối thủ RẺ hơn Long Vân: {json.dumps(cheaper_items[:10], ensure_ascii=False)}
- TLD Long Vân RẺ hơn đối thủ: {json.dumps(expensive_items[:10], ensure_ascii=False)}
- So sánh Tổng Chi Phí 2 Năm (Đăng ký + Gia hạn): {json.dumps(comparison_2yr[:10], ensure_ascii=False)}
{tld_avail_summary}

YÊU CẦU PHÂN TÍCH:
Hãy phân tích sắc bén, chính xác theo góc nhìn chuyên gia kinh doanh và trả về ĐÚNG định dạng JSON sau (tuyệt đối không có văn bản nào ngoài JSON):

{{
    "danh_gia_tinh_huong": "Đánh giá chính xác ý đồ đối thủ (Ví dụ: Ép giá gia hạn để lấy lời bù lỗ năm 1, hay tung khuyến mãi chớp thời cơ). Phân tích rõ lợi thế/nguy cơ của Long Vân.",
    "vi_the_canh_tranh": "Tóm tắt sắc bén vị thế Long Vân (Ví dụ: Long Vân đang thắng áp đảo ở .vn, .com.vn về tổng chi phí 2 năm nhưng bị ép ở các TLD ngách .pro.vn, .id.vn).",
    "ke_hoach_hanh_dong_tung_buoc": [
        "Bước 1 [Điều chỉnh giá/Ưu đãi]: (Nêu rõ hành động cụ thể, ví dụ giảm bao nhiêu % hoặc tặng voucher cho TLD nào)",
        "Bước 2 [Truyền thông & Marketing]: (Nêu rõ thông điệp Marketing cần đánh mạnh, ví dụ nhấn mạnh gia hạn .vn rẻ hơn đối thủ 52k)",
        "Bước 3 [Mở rộng danh mục/Dịch vụ]: (Gợi ý cụ thể TLD tiềm năng nên nhập về hoặc combo đi kèm)",
        "Bước 4 [Đo lường & Kiểm soát]: (Thời gian đánh giá lại hiệu quả)"
    ],
    "goi_y_tld_chi_tiet": "Danh sách 3-5 TLD cụ thể Long Vân cần ưu tiên hành động ngay."
}}
"""
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for model in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                res = requests.post(url, json=payload, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    analysis_text = data['candidates'][0]['content']['parts'][0]['text'].strip()

                    try:
                        ai_json = json.loads(analysis_text)

                        # Lưu vào Cache
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(ai_json, f, ensure_ascii=False, indent=4)
                        logger.info(f"AI Cache Miss - Saved to cache: {data_hash}")

                        return self._format_ai_response(ai_json, provider_name, prod_title)
                    except json.JSONDecodeError:
                        logger.error(f"Gemini returned invalid JSON: {analysis_text}")
                        return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability)
                else:
                    logger.warning(f"Gemini API returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.error(f"Exception during Gemini API call ({model}): {e}")

        logger.info("All Gemini models failed, falling back to rule-based AI")
        return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability)

    def _format_ai_response(self, ai_json: dict, provider_name: str, prod_title: str) -> str:
        """Định dạng JSON thành Markdown Telegram/Email đẹp mắt"""
        lines = []
        lines.append(f"🎯 *ĐÁNH GIÁ TÌNH HUỐNG THỊ TRƯỜNG ({provider_name.upper()}):*")
        lines.append(ai_json.get("danh_gia_tinh_huong", ai_json.get("ket_luan_chung", "")))

        lines.append("\n⚖️ *VỊ THẾ CẠNH TRANH CỦA LONG VÂN:*")
        lines.append(ai_json.get("vi_the_canh_tranh", ai_json.get("so_sanh_vi_the", "")))

        lines.append("\n🗺️ *KẾ HOẠCH TỔNG THỂ & HƯỚNG ĐI TỪNG BƯỚC:*")
        steps = ai_json.get("ke_hoach_hanh_dong_tung_buoc", ai_json.get("tu_van_huong_di", []))
        if isinstance(steps, list):
            for step in steps:
                lines.append(f"• {step}")
        else:
            lines.append(str(steps))

        tld_rec = ai_json.get("goi_y_tld_chi_tiet", ai_json.get("tld_recommendation", ""))
        if tld_rec:
            lines.append(f"\n🏷️ *HÀNH ĐỘNG TLD ƯU TIÊN:*")
            lines.append(tld_rec)

        return "\n".join(lines)

    def _fallback_rule_based(self, provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability=None) -> str:
        insights = []
        insights.append(f"🎯 *ĐÁNH GIÁ TÌNH HUỐNG THỊ TRƯỜNG ({provider_name.upper()}):*")
        if price_changes:
            decreases = [item for item in price_changes if item.get("new_price", 0) < item.get("old_price", 0)]
            increases = [item for item in price_changes if item.get("new_price", 0) > item.get("old_price", 0)]
            if decreases:
                item_names = ", ".join([d.get('tld', d.get('plan_name', '')) for d in decreases])
                insights.append(f"• {provider_name} đang hạ giá chiến lược tại nhóm ({item_names}) để gia tăng áp lực thị phần.")
            if increases:
                item_names = ", ".join([i.get('tld', i.get('plan_name', '')) for i in increases])
                insights.append(f"• {provider_name} điều chỉnh tăng giá tại nhóm ({item_names}) nhằm bù đắp chi phí & tối ưu biên lợi nhuận.")
        else:
            insights.append(f"• Bảng giá {provider_name} duy trì ổn định. Chưa phát hiện đợt điều chỉnh giá niêm yết mới.")

        insights.append("\n⚖️ *VỊ THẾ CẠNH TRANH CỦA LONG VÂN:*")
        if cheaper_items:
            cheaper_tlds = list(set([c.get('tld', c.get('plan_name', '')) for c in cheaper_items]))
            insights.append(f"⚠️ Đối thủ đang có ưu thế giá hơn Long Vân ở nhóm: `{', '.join(cheaper_tlds[:8])}`.")
        if expensive_items:
            expensive_tlds = list(set([e.get('tld', e.get('plan_name', '')) for e in expensive_items]))
            insights.append(f"✅ Long Vân giữ ưu thế giá gia hạn/tổng chi phí tốt hơn đối thủ tại nhóm: `{', '.join(expensive_tlds[:8])}`.")

        insights.append("\n🗺️ *KẾ HOẠCH TỔNG THỂ & HƯỚNG ĐI TỪNG BƯỚC FOR LONG VÂN:*")
        insights.append("• **Bước 1 [Chính sách Giá đối ứng]**: Tung chương trình tặng Voucher 50.000đ khi đăng ký/gia hạn nhóm TLD đang chịu ép giá.")
        insights.append("• **Bước 2 [Chiến dịch Marketing]**: Tập trung quảng bá thông điệp *'Gia hạn tên miền .vn tại Long Vân tiết kiệm 52.000đ/năm so với đối thủ'*. ")
        insights.append("• **Bước 3 [Đóng gói Combo Dịch vụ]**: Tặng kèm Email Server Pro 1GB hoặc DNSSEC miễn phí để tăng giá trị cạnh tranh.")
        insights.append("• **Bước 4 [Đo lường & Kiểm soát]**: Đánh giá tỷ lệ chuyển đổi khách hàng đăng ký mới sau 14 ngày áp dụng.")

        if tld_availability and tld_availability.get("competitor_exclusive"):
            comp_ex = tld_availability.get("competitor_exclusive", [])
            insights.append(f"\n🏷️ *HÀNH ĐỘNG TLD ƯU TIÊN:*")
            insights.append(f"Cân nhắc mở rộng thêm các đuôi tên miền thị trường có nhu cầu cao: `{', '.join(comp_ex[:5])}`.")
        return "\n".join(insights)
