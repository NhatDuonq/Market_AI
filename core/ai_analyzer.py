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
    Module phân tích chiến lược thị trường tự động bằng Gemini AI cho Long Vân Cloud (longvan.net).
    - Tự động đánh giá ý đồ cạnh tranh của đối thủ dựa trên dữ liệu đối soát 3 chiều.
    - Đề xuất chiến lược thương mại tự nhiên, cá nhân hóa theo đúng thế mạnh hạ tầng Long Vân.
    - Hỗ trợ Dynamic Fallback tự tính toán theo số liệu thực tế khi không có API key.
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
        longvan_comparison = changes.get("longvan_comparison", [])

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

        # 2. Gọi API hoặc fallback nếu thiếu cấu hình
        if not self.is_configured():
            logger.info("Gemini API Key missing, falling back to dynamic rule-based AI")
            return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability, longvan_comparison)

        # Lọc ra các mục so sánh 3 chiều chính
        comparison_2yr = [c for c in longvan_comparison if c.get("field") == "Tổng chi phí 2 năm"]
        comparison_reg = [c for c in longvan_comparison if c.get("field") == "Giá đăng ký"]
        comparison_renew = [c for c in longvan_comparison if c.get("field") == "Giá gia hạn"]

        # Trích xuất TLD độc quyền / bỏ lỡ
        lv_exclusive = tld_availability.get("longvan_exclusive", [])
        comp_exclusive = tld_availability.get("competitor_exclusive", [])

        # Xây dựng Prompt cung cấp TOÀN BỘ 100% dữ liệu cào được cho Gemini AI
        prompt = f"""
Bạn là Giám đốc Chiến lược Giá & Thị Phần (Chief Commercial Officer) của LONG VÂN CLOUD SOLUTION (longvan.net) tại Việt Nam.
Long Vân là nhà cung cấp hạ tầng Cloud Server, Cloud Hosting và Email Server doanh nghiệp uy tín hàng đầu.

Nhiệm vụ của bạn: Hãy phân tích độc lập, tự nhiên, sắc bén dựa trên TOÀN BỘ 100% dữ liệu đối soát cào được mới nhất giữa Long Vân và đối thủ cạnh tranh {provider_name.upper()}. Tuyệt đối KHÔNG lặp lại các câu mẫu khuôn thước hay dập khuôn.

TOÀN BỘ DỮ LIỆU ĐỐI SOÁT CÀO ĐƯỢC (FULL DATASET):
1. Đợt biến động giá mới nhất của đối thủ ({provider_name}):
{json.dumps(price_changes, ensure_ascii=False, indent=2) if price_changes else "Không có đợt điều chỉnh giá niêm yết mới trong vòng quét này."}

2. TLD mới ra mắt của đối thủ:
{json.dumps(new_items, ensure_ascii=False, indent=2) if new_items else "Chưa phát hiện TLD mới."}

3. TOÀN BỘ TLD đối thủ đang có giá thấp hơn Long Vân (Cheaper Items):
{json.dumps(cheaper_items, ensure_ascii=False, indent=2)}

4. TOÀN BỘ TLD Long Vân đang có ưu thế giá thấp hơn đối thủ (Expensive/Better Items):
{json.dumps(expensive_items, ensure_ascii=False, indent=2)}

5. TOÀN BỘ Độ phủ TLD (TLD Availability):
- TOÀN BỘ TLD độc quyền chỉ Long Vân bán (Tổng {len(lv_exclusive)} TLD): {json.dumps(lv_exclusive, ensure_ascii=False)}
- TOÀN BỘ TLD đối thủ có nhưng Long Vân chưa bán (Tổng {len(comp_exclusive)} TLD): {json.dumps(comp_exclusive, ensure_ascii=False)}

6. TOÀN BỘ Bảng đối soát chi tiết 3 chiều (Đăng ký, Gia hạn, Chuyển đổi, Tổng chi phí 2 năm trên tất cả TLD):
{json.dumps(longvan_comparison, ensure_ascii=False, indent=2)}

YÊU CẦU PHÂN TÍCH THỰC TẾ TRÊN DỮ LIỆU ĐẦY ĐỦ:
Phân tích tự nhiên, thẳng thắn, đưa ra nhận định kinh doanh thực tế dựa trên TOÀN BỘ bảng dữ liệu trên. Trả về ĐÚNG định dạng JSON sau (không thêm văn bản ngoài JSON):

{{
    "danh_gia_tinh_huong": "Nhận định ngắn gọn về chiến lược giá hiện tại của {provider_name}. Phân tích cách họ phân bổ giá đăng ký năm 1 vs giá gia hạn từ năm 2 để bẫy khách hàng hoặc lấy thị phần.",
    "vi_the_canh_tranh": "Phân tích thẳng thắn vị thế cạnh tranh của Long Vân dựa trên toàn bộ bảng dữ liệu. Nêu rõ Long Vân đang thắng ở đâu (ví dụ: các TLD chính như .vn, .com.vn) và đang bị ép ở đâu.",
    "ke_hoach_hanh_dong_tung_buoc": [
        "Bước 1 [Chính sách Giá đối ứng]: Đề xuất hành động điều chỉnh giá hoặc phát voucher đối ứng cụ thể dựa trên các con số chênh lệch thực tế.",
        "Bước 2 [Truyền thông & Marketing]: Đề xuất thông điệp truyền thông sắc bén xoay quanh tổng chi phí 2 năm hoặc giá gia hạn dài hạn.",
        "Bước 3 [Đóng gói Combo Dịch vụ Cloud]: Đề xuất combo đóng gói tên miền với sản phẩm thế mạnh của Long Vân (Cloud Server, Cloud Hosting, Email Server Pro).",
        "Bước 4 [Đo lường & Kiểm soát]: Tần suất và tiêu chí đánh giá hiệu quả."
    ],
    "goi_y_tld_chi_tiet": "Chỉ ra 3-5 TLD cụ thể mà Long Vân cần can thiệp ngay (kèm lý do ngắn gọn dựa trên số liệu)."
}}
"""
        models_to_try = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash-lite"]
        for model in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                res = requests.post(url, json=payload, timeout=20)
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
                        return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability, longvan_comparison)
                else:
                    logger.warning(f"Gemini API returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.error(f"Exception during Gemini API call ({model}): {e}")

        logger.info("All Gemini models failed, falling back to dynamic rule-based AI")
        return self._fallback_rule_based(provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability, longvan_comparison)

    def _format_ai_response(self, ai_json: dict, provider_name: str, prod_title: str) -> str:
        """Định dạng JSON thành Markdown đẹp mắt"""
        lines = []
        lines.append(f"🎯 *ĐÁNH GIÁ TÌNH HUỐNG THỊ TRƯỜNG ({provider_name.upper()}):*")
        lines.append(ai_json.get("danh_gia_tinh_huong", ""))

        lines.append("\n⚖️ *VỊ THẾ CẠNH TRANH CỦA LONG VÂN:*")
        lines.append(ai_json.get("vi_the_canh_tranh", ""))

        lines.append("\n🗺️ *KẾ HOẠCH TỔNG THỂ & HƯỚNG ĐI TỪNG BƯỚC:*")
        steps = ai_json.get("ke_hoach_hanh_dong_tung_buoc", [])
        if isinstance(steps, list):
            for step in steps:
                lines.append(f"• {step}")
        else:
            lines.append(str(steps))

        tld_rec = ai_json.get("goi_y_tld_chi_tiet", "")
        if tld_rec:
            lines.append(f"\n🏷️ *HÀNH ĐỘNG TLD ƯU TIÊN:*")
            lines.append(tld_rec)

        return "\n".join(lines)

    def _fallback_rule_based(self, provider_name, prod_title, price_changes, new_items, cheaper_items, expensive_items, tld_availability=None, longvan_comparison=None) -> str:
        """Dynamic Fallback: Tự động tính toán số liệu chênh lệch thực tế mà không cần chuỗi tĩnh gượng ép"""
        insights = []
        insights.append(f"🎯 *ĐÁNH GIÁ TÌNH HUỐNG THỊ TRƯỜNG ({provider_name.upper()}):*")
        
        if price_changes:
            decreases = [item for item in price_changes if item.get("new_price", 0) < item.get("old_price", 0)]
            increases = [item for item in price_changes if item.get("new_price", 0) > item.get("old_price", 0)]
            if decreases:
                item_names = ", ".join([d.get('tld', '') for d in decreases[:5]])
                insights.append(f"• {provider_name} đang kích cầu giảm giá tại nhóm `{item_names}` nhằm thu hút lượt đăng ký mới.")
            if increases:
                item_names = ", ".join([i.get('tld', '') for i in increases[:5]])
                insights.append(f"• {provider_name} điều chỉnh tăng giá tại nhóm `{item_names}` nhằm bù đắp chi phí gia hạn.")
        else:
            insights.append(f"• Bảng giá {provider_name} giữ nguyên ổn định. Đối thủ duy trì chiến lược giá hiện tại.")

        insights.append("\n⚖️ *VỊ THẾ CẠNH TRANH CỦA LONG VÂN:*")
        if cheaper_items:
            cheaper_tlds = list(set([c.get('tld', '') for c in cheaper_items if c.get('tld')]))
            insights.append(f"⚠️ Đối thủ đang có lợi thế giá thấp hơn Long Vân ở {len(cheaper_tlds)} TLD, tiêu biểu: `{', '.join(cheaper_tlds[:6])}`.")
        if expensive_items:
            expensive_tlds = list(set([e.get('tld', '') for e in expensive_items if e.get('tld')]))
            insights.append(f"✅ Long Vân giữ ưu thế giá tốt hơn đối thủ tại {len(expensive_tlds)} TLD, tiêu biểu: `{', '.join(expensive_tlds[:6])}`.")

        # Lấy chênh lệch thực tế của .vn nếu có
        vn_comp = [c for c in (longvan_comparison or []) if c.get("tld") == ".vn" and c.get("field") == "Giá gia hạn"]
        vn_diff_str = ""
        if vn_comp:
            diff_val = abs(vn_comp[0].get("diff_amount", 0))
            if diff_val > 0:
                vn_diff_str = f" (Long Vân tốt hơn {diff_val:,.0f}đ/năm đối với tên miền .vn)"

        insights.append("\n🗺️ *KẾ HOẠCH TỔNG THỂ & HƯỚNG ĐI TỪNG BƯỚC CỦA LONG VÂN:*")
        insights.append(f"• **Bước 1 [Chính sách Giá đối ứng]**: Rà soát lại biên lợi nhuận nhóm {len(cheaper_items)} TLD đang bị ép giá để xem xét tung Voucher đối ứng.")
        insights.append(f"• **Bước 2 [Truyền thông & Marketing]**: Đẩy mạnh thông điệp truyền thông về tính ổn định và giá gia hạn dài hạn{vn_diff_str}.")
        insights.append("• **Bước 3 [Đóng gói Combo Dịch vụ Cloud]**: Tận dụng thế mạnh hạ tầng Long Vân để tặng kèm Voucher Cloud Server hoặc Email Server Pro cho khách hàng mua tên miền.")
        insights.append("• **Bước 4 [Đo lường & Kiểm soát]**: Theo dõi biến động lượng đăng ký mới sau 14 ngày áp dụng.")

        if tld_availability and tld_availability.get("competitor_exclusive"):
            comp_ex = tld_availability.get("competitor_exclusive", [])
            insights.append(f"\n🏷️ *HÀNH ĐỘNG TLD ƯU TIÊN:*")
            insights.append(f"Cân nhắc nhập thêm các TLD có lượng tìm kiếm cao mà đối thủ đang có: `{', '.join(comp_ex[:5])}`.")

        return "\n".join(insights)
