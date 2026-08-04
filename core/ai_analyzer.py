import os
import json
import hashlib
import requests
import time
import random
import logging
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
    - Hỗ trợ Retry & Exponential Backoff (429, 503, 408).
    - Hỗ trợ Response Schema bắt buộc trả về đúng định dạng JSON.
    - Tự động Pre-processing tính toán chỉ số trước khi gửi cho AI (tiết kiệm token & TPM).
    - Sửa lỗi Hash Cache theo từng đối thủ & Kiểm tra chính xác dấu chênh lệch gia hạn .vn.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "YOUR_GEMINI_API_KEY")

    def _get_cache_path(self, data_hash: str) -> str:
        return os.path.join(CACHE_DIR, f"{data_hash}.json")

    def _generate_data_hash(self, provider_name: str, product_type: str, changes: dict) -> str:
        """Tạo MD5 hash dựa trên dữ liệu đối soát ổn định (bỏ qua timestamp/url linh hoạt)"""
        stable_changes = {
            "cheaper_count": len(changes.get("longvan_summary", {}).get("cheaper_items", [])),
            "expensive_count": len(changes.get("longvan_summary", {}).get("expensive_items", [])),
            "price_changes": [{"tld": c.get("tld"), "old_price": c.get("old_price"), "new_price": c.get("new_price")} for c in changes.get("price_changes", [])],
            "longvan_comparison": [{"tld": c.get("tld"), "field": c.get("field"), "comp_p": c.get("competitor_price"), "lv_p": c.get("longvan_price")} for c in changes.get("longvan_comparison", [])]
        }
        cache_input = {
            "provider": provider_name.lower().strip(),
            "product_type": product_type.lower().strip(),
            "data": stable_changes,
            "v": "v4_stable"
        }
        data_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.md5(data_str.encode('utf-8')).hexdigest()

    def analyze_domain_changes(self, provider_name: str, changes: dict, force_refresh: bool = False) -> str:
        return self.analyze_market_changes(provider_name, "domain", changes, force_refresh=force_refresh)

    def analyze_market_changes(self, provider_name: str, product_type: str, changes: dict, force_refresh: bool = False) -> str:
        price_changes = changes.get("price_changes", [])
        new_items = changes.get("new_tlds", [])
        lv_summary = changes.get("longvan_summary", {})
        cheaper_items = lv_summary.get("cheaper_items", [])
        expensive_items = lv_summary.get("expensive_items", [])
        tld_availability = changes.get("tld_availability", {})
        longvan_comparison = changes.get("longvan_comparison", [])

        # 1. Kiểm tra Cache chuẩn (nếu không ép buộc làm mới)
        data_hash = self._generate_data_hash(provider_name, product_type, changes)
        cache_path = self._get_cache_path(data_hash)
        if not force_refresh and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_res = json.load(f)
                logger.info(f"AI Cache Hit for {provider_name}: {data_hash}")
                return self._format_ai_response(cached_res, provider_name)
            except Exception as e:
                logger.warning(f"Failed to read cache {data_hash}: {e}")

        # 2. Python Pre-Processing (Tính toán chỉ số & Tổng hợp thông minh trước khi gửi cho AI)
        priority_tlds = [".vn", ".com.vn", ".com", ".net", ".edu.vn", ".org", ".info", ".biz"]
        key_comparisons = [c for c in longvan_comparison if c.get("tld") in priority_tlds]

        # Top TLD chênh lệch lớn nhất
        top_cheaper = sorted(cheaper_items, key=lambda x: abs(x.get("diff_amount", 0)), reverse=True)[:8]
        top_expensive = sorted(expensive_items, key=lambda x: abs(x.get("diff_amount", 0)), reverse=True)[:8]

        lv_exclusive = tld_availability.get("longvan_exclusive", [])
        comp_exclusive = tld_availability.get("competitor_exclusive", [])

        # 3. Dynamic Fallback nếu không có API Key
        if not self.is_configured():
            logger.info("Gemini API Key missing, using dynamic rule-based strategy engine")
            return self._fallback_rule_based(provider_name, price_changes, new_items, cheaper_items, expensive_items, tld_availability, longvan_comparison)

        # 4. Build Prompt tinh gọn với thông tin đã tính toán sẵn
        prompt = f"""
Bạn là Giám đốc Chiến lược Giá & Thị Phần (Chief Commercial Officer) của LONG VÂN CLOUD SOLUTION (longvan.net) tại Việt Nam.
Long Vân là nhà cung cấp hạ tầng Cloud Server, Cloud Hosting và Email Server doanh nghiệp uy tín hàng đầu.

Nhiệm vụ: Phân tích chiến lược giá và đưa ra nhận định kinh doanh thực tế đối soát với đối thủ {provider_name.upper()}.

TÓM TẮT DỮ LIỆU ĐỐI SOÁT:
- Đối thủ: {provider_name.upper()}
- Số TLD đối thủ có giá thấp hơn Long Vân: {len(cheaper_items)} TLD
- Số TLD Long Vân có giá thấp hơn đối thủ: {len(expensive_items)} TLD
- Số TLD chỉ Long Vân bán: {len(lv_exclusive)} TLD ({json.dumps(lv_exclusive[:10], ensure_ascii=False)})
- Số TLD chỉ đối thủ bán: {len(comp_exclusive)} TLD ({json.dumps(comp_exclusive[:10], ensure_ascii=False)})

CHI TIẾT MỤC QUAN TRỌNG:
1. Đợt biến động giá mới nhất: {json.dumps(price_changes[:5], ensure_ascii=False) if price_changes else "Không có"}
2. TLD mới đối thủ ra mắt: {json.dumps(new_items[:5], ensure_ascii=False) if new_items else "Không có"}
3. Top TLD đối thủ giá thấp hơn: {json.dumps(top_cheaper, ensure_ascii=False)}
4. Top TLD Long Vân ưu thế giá thấp hơn: {json.dumps(top_expensive, ensure_ascii=False)}
5. Đối soát các TLD trọng điểm (.vn, .com.vn, .com...): {json.dumps(key_comparisons, ensure_ascii=False)}

YÊU CẦU: Trả về JSON chứa đúng 4 trường được yêu cầu, phân tích thực tế, tự nhiên, không lặp lại câu mẫu.
"""

        # Structured Response Schema
        json_schema = {
            "type": "OBJECT",
            "properties": {
                "danh_gia_tinh_huong": {"type": "STRING"},
                "vi_the_canh_tranh": {"type": "STRING"},
                "ke_hoach_hanh_dong_tung_buoc": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "goi_y_tld_chi_tiet": {"type": "STRING"}
            },
            "required": [
                "danh_gia_tinh_huong",
                "vi_the_canh_tranh",
                "ke_hoach_hanh_dong_tung_buoc",
                "goi_y_tld_chi_tiet"
            ]
        }

        # Model list hỗ trợ Stable & Lite Models
        models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-3.6-flash"]

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": json_schema
                }
            }

            # Retry với Exponential Backoff (1s -> 2s -> 4s + random jitter)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    res = requests.post(url, json=payload, timeout=(5, 40))

                    if res.status_code == 200:
                        data = res.json()
                        text = self._extract_text_from_response(data)
                        if not text:
                            logger.warning(f"Model {model} returned empty response.")
                            break

                        try:
                            ai_json = json.loads(text)
                            if all(k in ai_json for k in ["danh_gia_tinh_huong", "vi_the_canh_tranh", "ke_hoach_hanh_dong_tung_buoc", "goi_y_tld_chi_tiet"]):
                                # Save to Cache
                                with open(cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(ai_json, f, ensure_ascii=False, indent=4)
                                logger.info(f"AI Analysis Successful ({model}) - Cached: {data_hash}")
                                return self._format_ai_response(ai_json, provider_name)
                            else:
                                logger.warning(f"Model {model} JSON missing required keys: {text}")
                                break
                        except json.JSONDecodeError:
                            logger.error(f"Model {model} output is not valid JSON: {text}")
                            continue  # Thử tiếp model khác chứ không dừng ngay lập tức

                    elif res.status_code in [429, 503, 408]:
                        wait_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                        logger.warning(f"Gemini API status {res.status_code} ({model}). Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue

                    else:
                        logger.warning(f"Gemini API model {model} returned status {res.status_code}: {res.text[:200]}")
                        break

                except Exception as e:
                    logger.error(f"Exception during Gemini API request ({model}): {e}")
                    break

        logger.info("All Gemini API models failed/exhausted, using dynamic rule-based fallback")
        return self._fallback_rule_based(provider_name, price_changes, new_items, cheaper_items, expensive_items, tld_availability, longvan_comparison)

    def _extract_text_from_response(self, data: dict) -> str:
        """Trích xuất dữ liệu text an toàn từ Gemini response"""
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            text_parts = [p.get("text", "") for p in parts if p.get("text")]
            return "".join(text_parts).strip()
        except Exception as e:
            logger.error(f"Error parsing Gemini response structure: {e}")
            return ""

    def _format_ai_response(self, ai_json: dict, provider_name: str) -> str:
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

    def _fallback_rule_based(self, provider_name, price_changes, new_items, cheaper_items, expensive_items, tld_availability=None, longvan_comparison=None) -> str:
        """Dynamic Fallback: Tự động tính toán số liệu chênh lệch thực tế mà không cần chuỗi tĩnh gượng ép"""
        insights = []
        insights.append(f"🎯 *ĐÁNH GIÁ TÌNH HUỐNG THỊ TRƯỜNG ({provider_name.upper()}):*")
        
        if price_changes:
            decreases = [item for item in price_changes if item.get("new_price", 0) < item.get("old_price", 0)]
            increases = [item for item in price_changes if item.get("new_price", 0) > item.get("old_price", 0)]
            if decreases:
                item_names = ", ".join([d.get('tld', '') for d in decreases[:5]])
                insights.append(f"• {provider_name} đang giảm giá tại nhóm `{item_names}` nhằm thu hút lượt đăng ký mới.")
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

        # Kiểm tra chính xác quy ước dấu của diff_amount:
        # diff_amount = competitor_price - longvan_price
        # diff > 0 => Giá đối thủ > Giá Long Vân (Long Vân thấp hơn diff_val)
        # diff < 0 => Giá đối thủ < Giá Long Vân (Long Vân cao hơn abs(diff_val))
        vn_comp = [c for c in (longvan_comparison or []) if c.get("tld") == ".vn" and c.get("field") == "Giá gia hạn"]
        vn_diff_str = ""
        if vn_comp:
            diff_val = vn_comp[0].get("diff_amount", 0)
            if diff_val > 0:
                vn_diff_str = f" (Long Vân có giá gia hạn thấp hơn đối thủ {diff_val:,.0f}đ/năm)"
            elif diff_val < 0:
                vn_diff_str = f" (Long Vân có giá gia hạn cao hơn đối thủ {abs(diff_val):,.0f}đ/năm)"

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
