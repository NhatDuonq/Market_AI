import os
import sys
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.database import Database
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:
    MongoClient = None
    Database = None

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/market_ai")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "market_ai")


class MongoDB:
    _instance: Optional["MongoDB"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDB, cls).__new__(cls)
            cls._instance._client = None
            cls._instance._db = None
        return cls._instance

    def connect(self) -> Optional[Database]:
        if MongoClient is None:
            logger.error("❌ pymongo chưa được cài đặt. Vui lòng chạy `pip install pymongo`")
            return None

        if self._db is not None:
            return self._db

        try:
            self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            # Test connection
            self._client.admin.command('ping')
            self._db = self._client[MONGO_DB_NAME]
            logger.info(f"✅ Kết nối MongoDB thành công: {MONGO_URI} (DB: {MONGO_DB_NAME})")
            self.init_indexes()
            self.seed_initial_shared_data()
            return self._db
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"⚠️ Không thể kết nối MongoDB: {e}. Hệ thống sẽ sử dụng JSON File Fallback.")
            return None

    @property
    def db(self) -> Optional[Database]:
        if self._db is None:
            return self.connect()
        return self._db

    def is_connected(self) -> bool:
        return self.db is not None

    def get_collection(self, collection_name: str):
        database = self.db
        if database is not None:
            return database[collection_name]
        return None

    # Collection Accessors
    @property
    def providers(self):
        return self.get_collection("providers")

    @property
    def users(self):
        return self.get_collection("users")

    @property
    def otps(self):
        return self.get_collection("otps")

    @property
    def refresh_tokens(self):
        return self.get_collection("refresh_tokens")

    @property
    def product_categories(self):
        return self.get_collection("product_categories")

    @property
    def normalized_products(self):
        return self.get_collection("normalized_products")

    @property
    def price_history(self):
        return self.get_collection("price_history")

    @property
    def ai_insights(self):
        return self.get_collection("ai_insights")

    @property
    def raw_snapshots(self):
        return self.get_collection("raw_snapshots")

    def init_indexes(self):
        """Khởi tạo Chỉ mục (Indexes) tối ưu tốc độ truy vấn."""
        database = self.db
        if database is None:
            return

        try:
            # 1. Collection Providers
            database.providers.create_index([("code", ASCENDING)], unique=True)

            # 2. Collection Users
            database.users.create_index([("email", ASCENDING)], unique=True)

            # 3. Collection Product Categories
            database.product_categories.create_index([("code", ASCENDING)], unique=True)

            # 4. Collection Normalized Products (Polymorphic)
            database.normalized_products.create_index([
                ("provider_code", ASCENDING),
                ("category", ASCENDING),
                ("product_key", ASCENDING)
            ], unique=True)
            database.normalized_products.create_index([("scraped_at", DESCENDING)])

            # 5. Collection Price History (Time-series analytics)
            database.price_history.create_index([
                ("provider_code", ASCENDING),
                ("category", ASCENDING),
                ("product_key", ASCENDING),
                ("detected_at", DESCENDING)
            ])

            # 6. Collection AI Insights
            database.ai_insights.create_index([("created_at", DESCENDING)])

            logger.info("⚡ Khởi tạo Indexes MongoDB thành công!")
        except Exception as e:
            logger.error(f"❌ Lỗi khi khởi tạo Indexes MongoDB: {e}")

    def seed_initial_shared_data(self):
        """Khởi tạo Dữ liệu dùng chung hạt nhân (Shared Providers & Categories)."""
        database = self.db
        if database is None:
            return

        # 1. Seed Shared Providers
        initial_providers = [
            {"code": "longvan", "name": "Long Vân Cloud (Benchmark)", "website": "https://longvan.net", "status": "active", "is_benchmark": True},
            {"code": "matbao", "name": "Mắt Bão", "website": "https://matbao.net", "status": "active", "is_benchmark": False},
            {"code": "pavietnam", "name": "PA Việt Nam", "website": "https://pavietnam.vn", "status": "active", "is_benchmark": False},
            {"code": "inet", "name": "iNET", "website": "https://inet.vn", "status": "active", "is_benchmark": False},
            {"code": "vietnix", "name": "Vietnix Cloud", "website": "https://vietnix.vn", "status": "active", "is_benchmark": False}
        ]
        for p in initial_providers:
            database.providers.update_one(
                {"code": p["code"]},
                {"$setOnInsert": p},
                upsert=True
            )

        # 2. Seed Product Categories
        initial_categories = [
            {
                "code": "domain",
                "name": "Tên miền",
                "schema_fields": ["tld", "reg_price", "renew_price", "total_2yr"],
                "description": "Giám sát & So sánh giá Đăng ký, Gia hạn tên miền 3 chiều"
            },
            {
                "code": "vps",
                "name": "Cloud VPS",
                "schema_fields": ["package_name", "cpu", "ram", "disk", "bandwidth", "price_monthly"],
                "description": "Giám sát & So sánh cấu hình và giá gói Máy chủ ảo Cloud VPS"
            },
            {
                "code": "hosting",
                "name": "Web Hosting",
                "schema_fields": ["package_name", "disk", "domains", "bandwidth", "price_monthly"],
                "description": "Giám sát & So sánh gói lưu trữ Web Hosting"
            }
        ]
        for c in initial_categories:
            database.product_categories.update_one(
                {"code": c["code"]},
                {"$setOnInsert": c},
                upsert=True
            )


db_mongo = MongoDB()


def get_mongo_db() -> Optional[Database]:
    return db_mongo.db
