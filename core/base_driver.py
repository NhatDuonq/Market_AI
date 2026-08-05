import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from core.db_mongo import db_mongo

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


def get_vn_now_iso():
    return datetime.now(VN_TZ).isoformat()


class BaseProductDriver(ABC):
    """
    Lớp cơ sở (Abstract Base Class) cho tất cả các Driver Plugin cào dữ liệu theo Sản phẩm & Nhà cung cấp.
    Áp dụng Template Method Pattern & Strategy Pattern.
    """

    def __init__(self, provider_code: str, category: str, target_url: str):
        self.provider_code = provider_code
        self.category = category
        self.target_url = target_url

    @abstractmethod
    def fetch_raw_data(self) -> Any:
        """Thực hiện cào dữ liệu thô từ Website (Playwright / Request / Tooltipster API)."""
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Phân tích dữ liệu thô và trả về danh sách các sản phẩm đã được trích xuất."""
        pass

    def normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa một item theo Polymorphic Schema của MongoDB."""
        item["provider_code"] = self.provider_code
        item["category"] = self.category
        if "scraped_at" not in item:
            item["scraped_at"] = get_vn_now_iso()
        return item

    def save_to_mongo(self, items: List[Dict[str, Any]]) -> bool:
        """
        Lưu danh sách sản phẩm đã chuẩn hóa vào MongoDB `normalized_products` và tự động ghi vết biến động giá vào `price_history`.
        """
        if not db_mongo.is_connected():
            logger.warning(f"⚠️ MongoDB không kết nối. Không thể lưu dữ liệu cào {self.provider_code}_{self.category}")
            return False

        col_normalized = db_mongo.normalized_products
        col_history = db_mongo.price_history
        now_str = get_vn_now_iso()

        saved_count = 0
        for raw_item in items:
            normalized = self.normalize_item(raw_item)
            product_key = normalized.get("product_key") or normalized.get("tld") or normalized.get("package_name")

            if not product_key:
                continue

            query = {
                "provider_code": self.provider_code,
                "category": self.category,
                "product_key": product_key
            }

            # Check existing item to track price history
            existing = col_normalized.find_one(query)
            if existing:
                # Track price change
                old_attr = existing.get("attributes", {})
                new_attr = normalized.get("attributes", {})
                
                # Check price fields depending on category
                old_price = old_attr.get("price_monthly") or old_attr.get("reg_price")
                new_price = new_attr.get("price_monthly") or new_attr.get("reg_price")

                if old_price is not None and new_price is not None and old_price != new_price:
                    change_type = "price_increase" if new_price > old_price else "price_decrease"
                    diff_amount = new_price - old_price
                    col_history.insert_one({
                        "provider_code": self.provider_code,
                        "category": self.category,
                        "product_key": product_key,
                        "old_price": old_price,
                        "new_price": new_price,
                        "diff_amount": diff_amount,
                        "change_type": change_type,
                        "detected_at": now_str
                    })
                    logger.info(f"🚨 Phát hiện biến động giá [{self.provider_code}_{self.category}] {product_key}: {old_price} -> {new_price}")

            # Upsert into normalized_products
            normalized["updated_at"] = now_str
            col_normalized.update_one(query, {"$set": normalized}, upsert=True)
            saved_count += 1

        logger.info(f"✅ Đã lưu {saved_count} items [{self.provider_code}_{self.category}] vào MongoDB.")
        return True

    def run(self) -> List[Dict[str, Any]]:
        """
        Orchestration method: Chạy toàn bộ quy trình cào, parse và lưu trữ vào MongoDB.
        """
        logger.info(f"🚀 Bắt đầu Driver Plugin: {self.provider_code} - {self.category} ({self.target_url})")
        try:
            raw = self.fetch_raw_data()
            parsed = self.parse_data(raw)
            self.save_to_mongo(parsed)
            return parsed
        except Exception as e:
            logger.error(f"❌ Lỗi khi thực thi Driver [{self.provider_code}_{self.category}]: {e}", exc_info=True)
            return []
