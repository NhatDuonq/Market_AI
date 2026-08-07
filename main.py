import os
import sys
import argparse
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

import json

from providers.matbao.domain import MatBaoDomainProvider
from providers.pavietnam.domain import PaVietnamDomainProvider
from providers.longvan.domain import LongVanDomainProvider
from providers.vietnix.domain import VietnixDomainProvider

PROVIDERS_REGISTRY = {
    ("longvan", "domain"): LongVanDomainProvider,
    ("matbao", "domain"): MatBaoDomainProvider,
    ("pavietnam", "domain"): PaVietnamDomainProvider,
    ("vietnix", "domain"): VietnixDomainProvider,
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "crawler_targets.json")

def load_crawler_targets() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Lỗi đọc file config {CONFIG_PATH}: {e}")
    return {}

def is_target_enabled(provider_name: str, product_type: str) -> bool:
    targets = load_crawler_targets()
    p_config = targets.get(provider_name.lower(), {})
    prod_config = p_config.get("products", {}).get(product_type.lower(), {})
    return prod_config.get("enabled", True)

def run_specific(provider_name: str, product_type: str, ignore_toggle: bool = False, force_notify: bool = False):
    p_name = provider_name.lower()
    prod_type = product_type.lower()
    key = (p_name, prod_type)

    if not ignore_toggle and not is_target_enabled(p_name, prod_type):
        print(f"⏸️ [CRAWLER TARGETS] Bỏ qua [{p_name.upper()} - {prod_type.upper()}] vì công tắc đang TẮT trên Dashboard.")
        return

    if key in PROVIDERS_REGISTRY:
        print(f"🚀 Kích hoạt cào dữ liệu cho [{p_name.upper()} - {prod_type.upper()}]...")
        provider_cls = PROVIDERS_REGISTRY[key]
        instance = provider_cls()
        instance.run(force_notify=force_notify)
    else:
        print(f"❌ Không tìm thấy provider [{provider_name}] với sản phẩm [{product_type}].")
        print(f"👉 Danh sách khả dụng: {list(PROVIDERS_REGISTRY.keys())}")

def _run_single_target(p: str, prod: str, cls, force_notify: bool = False):
    try:
        print(f"\n--- Running [{p.upper()} - {prod.upper()}] ---")
        instance = cls()
        instance.run(force_notify=force_notify)
    except Exception as e:
        print(f"❌ Lỗi khi chạy [{p} - {prod}]: {e}")

def run_all(force_notify: bool = False, ignore_toggle: bool = False):
    print(f"🚀 Bắt đầu lượt quét cho TẤT CẢ nhà cung cấp (force_notify={force_notify}, ignore_toggle={ignore_toggle})...")
    import concurrent.futures

    # QUAN TRỌNG: Chạy Long Vân (Benchmark) TRƯỚC để cập nhật snapshot chuẩn
    lv_key = ("longvan", "domain")
    if lv_key in PROVIDERS_REGISTRY and (ignore_toggle or is_target_enabled("longvan", "domain")):
        print("📌 [BENCHMARK] Chạy cào Long Vân trước để cập nhật dữ liệu chuẩn...")
        _run_single_target("longvan", "domain", PROVIDERS_REGISTRY[lv_key], force_notify=force_notify)
    
    # Sau đó chạy các đối thủ song song
    tasks = []
    for (p, prod), cls in PROVIDERS_REGISTRY.items():
        if p == "longvan":
            continue  # Đã chạy ở trên
        if not ignore_toggle and not is_target_enabled(p, prod):
            print(f"⏸️ [SKIP] Bỏ qua [{p.upper()} - {prod.upper()}] (Công tắc cào: TẮT)")
            continue
        tasks.append((p, prod, cls))
        
    if not tasks:
        print("⚠️ Không có mục tiêu đối thủ nào được bật.")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_run_single_target, p, prod, cls, force_notify) for p, prod, cls in tasks]
        concurrent.futures.wait(futures)
    print("✅ Đã hoàn tất lượt quét cho tất cả nhà cung cấp.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market AI CLI Orchestrator")
    parser.add_argument("--provider", "-p", type=str, help="Tên nhà cung cấp (VD: longvan, matbao, pavietnam)")
    parser.add_argument("--product", "-prod", type=str, help="Tên sản phẩm (VD: domain)")
    parser.add_argument("--all", "-a", action="store_true", help="Chạy quét tất cả các nhà cung cấp")
    parser.add_argument("--force", "-f", action="store_true", help="Ép cào bất chấp trạng thái công tắc")

    args = parser.parse_args()

    if args.all or (not args.provider and not args.product):
        run_all(force_notify=args.force, ignore_toggle=args.force)
    elif args.provider and args.product:
        run_specific(args.provider, args.product, ignore_toggle=args.force, force_notify=args.force)
    else:
        print("⚠️ Vui lòng chỉ định cả --provider và --product (Ví dụ: python main.py -p matbao -prod domain), hoặc dùng --all.")
