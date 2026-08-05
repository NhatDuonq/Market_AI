import os
import sys
import json
import logging
import importlib
from typing import Dict, List, Type, Optional
from core.base_driver import BaseProductDriver
from core.db_mongo import db_mongo

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(project_root, "config", "crawler_targets.json")


class PluginManager:
    """
    Quản lý Động các Driver Plugin Cào Dữ liệu Đa Sản phẩm / Đa Nhà Cung Cấp.
    Tự động Load và Kích hoạt Driver theo Cấu hình Config `crawler_targets.json`.
    """

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self._drivers_registry: Dict[str, BaseProductDriver] = {}
        self.load_config_and_register_plugins()

    def _load_config(self) -> Dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Lỗi khi đọc file config crawler targets: {e}")
        return {}

    def is_target_enabled(self, provider_code: str, category: str) -> bool:
        cfg = self._load_config()
        provider_cfg = cfg.get(provider_code, {})
        products = provider_cfg.get("products", {})
        prod_cfg = products.get(category, {})
        return prod_cfg.get("enabled", True)

    def load_config_and_register_plugins(self):
        """Tự động khám phá và khởi tạo Driver Plugins từ thư mục `providers/`."""
        cfg = self._load_config()
        self._drivers_registry.clear()

        for provider_code, provider_info in cfg.items():
            products = provider_info.get("products", {})
            for category, prod_info in products.items():
                if not prod_info.get("enabled", True):
                    continue

                module_path = f"providers.{provider_code}.{category}"
                try:
                    module = importlib.import_module(module_path)
                    # Tìm Class kế thừa từ BaseProductDriver trong module
                    driver_class = None
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, BaseProductDriver) and attr is not BaseProductDriver:
                            driver_class = attr
                            break

                    if driver_class:
                        target_url = prod_info.get("url", "")
                        instance = driver_class(provider_code=provider_code, category=category, target_url=target_url)
                        registry_key = f"{provider_code}_{category}"
                        self._drivers_registry[registry_key] = instance
                        logger.info(f"✅ Đã nạp Driver Plugin: [{registry_key}] -> {driver_class.__name__}")
                except ModuleNotFoundError:
                    logger.debug(f"ℹ️ Module {module_path} chưa tạo driver class mới (sử dụng legacy scraper).")
                except Exception as e:
                    logger.error(f"❌ Lỗi khi nạp Driver Plugin {module_path}: {e}")

    def get_registered_drivers(self) -> Dict[str, BaseProductDriver]:
        return self._drivers_registry

    def run_driver(self, provider_code: str, category: str) -> List[Dict]:
        key = f"{provider_code}_{category}"
        driver = self._drivers_registry.get(key)
        if driver:
            return driver.run()
        logger.warning(f"⚠️ Không tìm thấy Driver Plugin cho [{key}]")
        return []

    def run_all_drivers(self) -> Dict[str, List[Dict]]:
        results = {}
        for key, driver in self._drivers_registry.items():
            logger.info(f"⚡ Thực thi Driver Plugin [{key}]...")
            results[key] = driver.run()
        return results


plugin_manager = PluginManager()
