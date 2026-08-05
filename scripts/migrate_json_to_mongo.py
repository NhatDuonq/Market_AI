import os
import sys
import glob
import json
import logging
from datetime import datetime, timezone, timedelta

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.db_mongo import db_mongo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = os.path.join(project_root, "storage", "snapshots")
USERS_DB_DIR = os.path.join(project_root, "storage", "users_db")


def parse_snapshot_filename(filename: str):
    base = os.path.basename(filename).replace("_snapshot.json", "")
    parts = base.split("_")
    if len(parts) >= 2:
        provider = parts[0]
        category = parts[1]
        return provider, category
    return None, None


def migrate_snapshots():
    logger.info("==================================================")
    logger.info("🚀 BẮT ĐẦU MIGRATE SNAPSHOTS JSON SANG MONGODB")
    logger.info("==================================================")

    if not db_mongo.is_connected():
        logger.error("❌ Không thể kết nối MongoDB. Vui lòng bật dịch vụ Mongo (ví dụ: `docker compose up -d mongo`).")
        return

    snapshot_files = glob.glob(os.path.join(SNAPSHOTS_DIR, "*_snapshot.json"))
    logger.info(f"📁 Tìm thấy {len(snapshot_files)} file snapshots JSON.")

    col_normalized = db_mongo.normalized_products
    col_raw = db_mongo.raw_snapshots

    total_migrated = 0

    for filepath in snapshot_files:
        filename = os.path.basename(filepath)
        provider, category = parse_snapshot_filename(filename)

        if not provider or not category:
            logger.warning(f"⚠️ Bỏ qua file không đúng định dạng tên: {filename}")
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            updated_at = data.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            url = data.get("url", "")
            items = data.get("items", [])

            # 1. Audit raw snapshot log
            col_raw.update_one(
                {"filename": filename},
                {"$set": {
                    "filename": filename,
                    "provider": provider,
                    "category": category,
                    "url": url,
                    "item_count": len(items),
                    "raw_data": data,
                    "migrated_at": datetime.now().isoformat()
                }},
                upsert=True
            )

            # 2. Normalize and Upsert items
            for item in items:
                product_key = None
                attributes = {}

                if category == "domain":
                    product_key = item.get("tld")
                    reg_price = item.get("register_price") or item.get("reg_price") or 0.0
                    renew_price = item.get("renew_price") or 0.0
                    total_2yr = reg_price + renew_price if reg_price and renew_price else reg_price
                    attributes = {
                        "tld": product_key,
                        "reg_price": reg_price,
                        "renew_price": renew_price,
                        "transfer_price": item.get("transfer_price"),
                        "total_2yr": total_2yr,
                        "promo_note": item.get("promo_note")
                    }
                elif category == "vps":
                    product_key = item.get("plan_id") or item.get("name")
                    attributes = {
                        "package_name": item.get("name") or item.get("plan_id"),
                        "cpu": item.get("v_cpu") or item.get("cpu"),
                        "ram": item.get("ram_gb") or item.get("ram"),
                        "disk": item.get("ssd_gb") or item.get("disk"),
                        "price_monthly": item.get("monthly_price") or item.get("price")
                    }
                elif category == "hosting":
                    product_key = item.get("plan_id") or item.get("name")
                    attributes = {
                        "package_name": item.get("name") or item.get("plan_id"),
                        "disk": item.get("ssd_gb") or item.get("disk"),
                        "domains": item.get("domains") or item.get("domain_count"),
                        "price_monthly": item.get("monthly_price") or item.get("price")
                    }
                else:
                    product_key = item.get("id") or item.get("name") or item.get("key")
                    attributes = item

                if not product_key:
                    continue

                doc = {
                    "provider_code": provider,
                    "category": category,
                    "product_key": product_key,
                    "attributes": attributes,
                    "target_url": url,
                    "scraped_at": updated_at,
                    "updated_at": datetime.now().isoformat()
                }

                col_normalized.update_one(
                    {
                        "provider_code": provider,
                        "category": category,
                        "product_key": product_key
                    },
                    {"$set": doc},
                    upsert=True
                )
                total_migrated += 1

            logger.info(f"  ✓ [{provider.upper()} - {category.upper()}] Migrated {len(items)} items từ {filename}")
        except Exception as e:
            logger.error(f"❌ Lỗi khi xử lý file {filename}: {e}")

    logger.info(f"\n🎉 HOÀN THÀNH: Đã lưu {total_migrated} sản phẩm vào collection `normalized_products`!")


def migrate_users():
    logger.info("\n👤 MIGRATE NGHƯỜI DÙNG SANG MONGODB...")
    if not db_mongo.is_connected():
        return

    users_file = os.path.join(USERS_DB_DIR, "users.json")
    if os.path.exists(users_file):
        try:
            with open(users_file, "r", encoding="utf-8") as f:
                users = json.load(f)

            col_users = db_mongo.users
            count = 0
            for u in users:
                email = u.get("email")
                if email:
                    col_users.update_one({"email": email}, {"$set": u}, upsert=True)
                    count += 1
            logger.info(f"  ✓ Migrated {count} tài khoản người dùng vào MongoDB collection `users`.")
        except Exception as e:
            logger.error(f"❌ Lỗi khi migrate người dùng: {e}")


if __name__ == "__main__":
    migrate_snapshots()
    migrate_users()
