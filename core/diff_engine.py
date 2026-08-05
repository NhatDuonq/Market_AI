import os
import json
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))

def get_vn_now():
    return datetime.now(VN_TZ)


class DiffEngine:
    """
    Engine so sánh Snapshot dữ liệu cũ và mới để phát hiện biến động giá, TLD mới,
    và phân tích Độ phủ TLD (TLD Availability) giữa Long Vân và đối thủ.
    """
    def __init__(self, snapshot_dir: str = None):
        if snapshot_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            snapshot_dir = os.path.join(project_root, "storage", "snapshots")
        self.snapshot_dir = snapshot_dir
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def _get_snapshot_filepath(self, provider_key: str) -> str:
        return os.path.join(self.snapshot_dir, f"{provider_key}_snapshot.json")

    def load_last_snapshot(self, provider_key: str) -> dict:
        # Try loading from MongoDB first
        from core.db_mongo import db_mongo
        if db_mongo.is_connected():
            try:
                parts = provider_key.split("_")
                provider_code = parts[0]
                category = parts[1] if len(parts) > 1 else "domain"
                cursor = db_mongo.normalized_products.find({
                    "provider_code": provider_code,
                    "category": category
                })
                docs = list(cursor)
                if docs:
                    items = []
                    url = docs[0].get("target_url", "")
                    updated_at = docs[0].get("scraped_at", "")
                    for d in docs:
                        attr = d.get("attributes", {})
                        if category == "domain":
                            items.append({
                                "tld": attr.get("tld") or d.get("product_key"),
                                "register_price": attr.get("reg_price"),
                                "renew_price": attr.get("renew_price"),
                                "transfer_price": attr.get("transfer_price"),
                                "promo_note": attr.get("promo_note")
                            })
                        elif category in ["vps", "hosting"]:
                            items.append({
                                "plan_id": d.get("product_key"),
                                "name": attr.get("package_name"),
                                "v_cpu": attr.get("cpu"),
                                "ram_gb": attr.get("ram"),
                                "ssd_gb": attr.get("disk"),
                                "monthly_price": attr.get("price_monthly")
                            })
                        else:
                            items.append(attr)
                    return {
                        "updated_at": updated_at,
                        "url": url,
                        "items": items
                    }
            except Exception as e:
                print(f"[DiffEngine] ⚠️ Lỗi đọc từ MongoDB cho {provider_key}: {e}")

        # JSON File Fallback
        filepath = self._get_snapshot_filepath(provider_key)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[DiffEngine] ⚠️ Lỗi đọc snapshot cũ {filepath}: {e}")
        return {}

    def save_snapshot(self, provider_key: str, data: dict):
        filepath = self._get_snapshot_filepath(provider_key)
        history_dir = os.path.join(self.snapshot_dir, "history")
        os.makedirs(history_dir, exist_ok=True)
        timestamp = get_vn_now().strftime("%Y%m%d_%H%M%S")
        history_filepath = os.path.join(history_dir, f"{provider_key}_{timestamp}.json")

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with open(history_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[DiffEngine] 💾 Đã cập nhật snapshot mới cho {provider_key} tại {filepath} và {history_filepath}")
        except Exception as e:
            print(f"[DiffEngine] ❌ Lỗi ghi snapshot {filepath}: {e}")

        # Save to MongoDB
        from core.db_mongo import db_mongo
        if db_mongo.is_connected():
            try:
                parts = provider_key.split("_")
                provider_code = parts[0]
                category = parts[1] if len(parts) > 1 else "domain"
                items = data.get("items", [])
                for item in items:
                    product_key = item.get("tld") or item.get("plan_id") or item.get("name")
                    if not product_key:
                        continue
                    db_mongo.normalized_products.update_one(
                        {
                            "provider_code": provider_code,
                            "category": category,
                            "product_key": product_key
                        },
                        {"$set": {
                            "provider_code": provider_code,
                            "category": category,
                            "product_key": product_key,
                            "attributes": item,
                            "target_url": data.get("url", ""),
                            "scraped_at": data.get("updated_at", get_vn_now().strftime("%Y-%m-%d %H:%M:%S"))
                        }},
                        upsert=True
                    )
                print(f"[DiffEngine] 🍃 Đã đồng bộ {len(items)} items sang MongoDB collection `normalized_products`.")
            except Exception as e:
                print(f"[DiffEngine] ⚠️ Lỗi đồng bộ MongoDB cho {provider_key}: {e}")

    def load_longvan_snapshot(self, product_type: str = "domain") -> dict:
        filepath = os.path.join(self.snapshot_dir, f"longvan_{product_type}_snapshot.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[DiffEngine] ⚠️ Lỗi đọc snapshot Long Vân {filepath}: {e}")
        return {}

    def save_longvan_snapshot(self, items: list, product_type: str = "domain", url: str = ""):
        filepath = os.path.join(self.snapshot_dir, f"longvan_{product_type}_snapshot.json")
        try:
            snapshot_data = {
                "updated_at": get_vn_now().strftime("%Y-%m-%d %H:%M:%S"),
                "url": url or "https://longvan.net/domain#bang-gia-ten-mien",
                "items": items
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
            print(f"[DiffEngine] 💾 Đã cập nhật snapshot Long Vân tại {filepath}")
        except Exception as e:
            print(f"[DiffEngine] ❌ Lỗi ghi snapshot Long Vân {filepath}: {e}")

    def analyze_tld_availability(self, provider_key: str) -> dict:
        """
        Phân tích Độ phủ TLD: So sánh tập hợp TLD mà Long Vân bán vs đối thủ.
        Returns:
            - longvan_exclusive: Những TLD chỉ Long Vân bán (lợi thế ngách).
            - competitor_exclusive: Những TLD chỉ đối thủ bán (Long Vân bỏ lỡ).
            - common: Những TLD cả hai bên cùng bán.
        """
        lv_snap = self.load_longvan_snapshot("domain")
        comp_snap = self.load_last_snapshot(provider_key)

        lv_tlds = {item["tld"].lower() for item in lv_snap.get("items", []) if "tld" in item}
        comp_tlds = {item["tld"].lower() for item in comp_snap.get("items", []) if "tld" in item}

        return {
            "longvan_exclusive": sorted(list(lv_tlds - comp_tlds)),
            "competitor_exclusive": sorted(list(comp_tlds - lv_tlds)),
            "common": sorted(list(lv_tlds & comp_tlds)),
            "longvan_total": len(lv_tlds),
            "competitor_total": len(comp_tlds),
        }

    def compare_domain_data(self, provider_key: str, current_items: list, url: str = "", save: bool = True) -> dict:
        """
        So sánh danh sách tên miền hiện tại với snapshot trước đó của đối thủ
        đồng thời so sánh trực tiếp với bảng giá niêm yết của Long Vân (3-Way Comparison).
        Bao gồm: Giá đăng ký, Giá gia hạn, Giá chuyển đổi, Tổng chi phí 2 năm.
        """
        last_snapshot = self.load_last_snapshot(provider_key)
        last_items_map = {item["tld"].lower(): item for item in last_snapshot.get("items", []) if "tld" in item}
        current_items_map = {item["tld"].lower(): item for item in current_items if "tld" in item}

        # Load snapshot Long Vân
        longvan_snapshot = self.load_longvan_snapshot("domain")
        longvan_items_map = {item["tld"].lower(): item for item in longvan_snapshot.get("items", []) if "tld" in item}

        price_changes = []
        new_tlds = []
        longvan_comparison = []

        for tld, cur_item in current_items_map.items():
            lv_item = longvan_items_map.get(tld, {})
            lv_reg = float(lv_item.get("register_price") or 0)
            lv_renew = float(lv_item.get("renew_price") or 0)
            lv_transfer = float(lv_item.get("transfer_price") or 0)

            cur_reg = float(cur_item.get("register_price") or 0)
            cur_renew = float(cur_item.get("renew_price") or 0)
            cur_transfer = float(cur_item.get("transfer_price") or 0)

            # Tổng chi phí 2 năm = Giá đăng ký năm 1 + Giá gia hạn năm 2
            cur_2yr = cur_reg + cur_renew
            lv_2yr = lv_reg + lv_renew

            if tld not in last_items_map:
                new_tlds.append({
                    **cur_item,
                    "longvan_register_price": lv_reg,
                    "longvan_renew_price": lv_renew,
                    "longvan_transfer_price": lv_transfer,
                })
            else:
                prev_item = last_items_map[tld]
                # Check register_price changes
                prev_reg = float(prev_item.get("register_price") or 0)
                if prev_reg > 0 and cur_reg > 0 and prev_reg != cur_reg:
                    diff_lv = cur_reg - lv_reg if lv_reg > 0 else 0
                    price_changes.append({
                        "tld": cur_item["tld"],
                        "field": "Giá đăng ký năm đầu",
                        "old_price": prev_reg,
                        "new_price": cur_reg,
                        "longvan_price": lv_reg,
                        "diff_vs_longvan": diff_lv,
                        "status_vs_longvan": "CHEAPER" if diff_lv < 0 else ("EXPENSIVE" if diff_lv > 0 else "EQUAL")
                    })

                # Check renew_price changes
                prev_renew = float(prev_item.get("renew_price") or 0)
                if prev_renew > 0 and cur_renew > 0 and prev_renew != cur_renew:
                    diff_lv = cur_renew - lv_renew if lv_renew > 0 else 0
                    price_changes.append({
                        "tld": cur_item["tld"],
                        "field": "Giá gia hạn",
                        "old_price": prev_renew,
                        "new_price": cur_renew,
                        "longvan_price": lv_renew,
                        "diff_vs_longvan": diff_lv,
                        "status_vs_longvan": "CHEAPER" if diff_lv < 0 else ("EXPENSIVE" if diff_lv > 0 else "EQUAL")
                    })

                # Check transfer_price changes
                prev_transfer = float(prev_item.get("transfer_price") or 0)
                if prev_transfer > 0 and cur_transfer > 0 and prev_transfer != cur_transfer:
                    diff_lv = cur_transfer - lv_transfer if lv_transfer > 0 else 0
                    price_changes.append({
                        "tld": cur_item["tld"],
                        "field": "Giá chuyển đổi",
                        "old_price": prev_transfer,
                        "new_price": cur_transfer,
                        "longvan_price": lv_transfer,
                        "diff_vs_longvan": diff_lv,
                        "status_vs_longvan": "CHEAPER" if diff_lv < 0 else ("EXPENSIVE" if diff_lv > 0 else "EQUAL")
                    })

            # Full 3-way comparison: Giá đăng ký
            prev_reg = float((last_items_map.get(tld, {}) or {}).get("register_price") or cur_reg or 0)
            if lv_reg > 0 and cur_reg > 0:
                diff_reg = cur_reg - lv_reg
                pct_reg = (diff_reg / lv_reg * 100) if lv_reg > 0 else 0
                longvan_comparison.append({
                    "tld": cur_item["tld"],
                    "field": "Giá đăng ký",
                    "plan_name": cur_item["tld"],
                    "old_price": prev_reg,
                    "competitor_price": cur_reg,
                    "competitor_diff": cur_reg - prev_reg,
                    "longvan_price": lv_reg,
                    "diff_amount": diff_reg,
                    "diff_pct": pct_reg,
                    "status": "CHEAPER" if diff_reg < 0 else ("EXPENSIVE" if diff_reg > 0 else "EQUAL")
                })

            # Full 3-way comparison: Giá gia hạn
            prev_renew = float((last_items_map.get(tld, {}) or {}).get("renew_price") or cur_renew or 0)
            if lv_renew > 0 and cur_renew > 0:
                diff_renew = cur_renew - lv_renew
                pct_renew = (diff_renew / lv_renew * 100) if lv_renew > 0 else 0
                longvan_comparison.append({
                    "tld": cur_item["tld"],
                    "field": "Giá gia hạn",
                    "plan_name": cur_item["tld"],
                    "old_price": prev_renew,
                    "competitor_price": cur_renew,
                    "competitor_diff": cur_renew - prev_renew,
                    "longvan_price": lv_renew,
                    "diff_amount": diff_renew,
                    "diff_pct": pct_renew,
                    "status": "CHEAPER" if diff_renew < 0 else ("EXPENSIVE" if diff_renew > 0 else "EQUAL")
                })

            # Full 3-way comparison: Giá chuyển đổi
            prev_transfer = float((last_items_map.get(tld, {}) or {}).get("transfer_price") or cur_transfer or 0)
            if lv_transfer > 0 and cur_transfer > 0:
                diff_transfer = cur_transfer - lv_transfer
                pct_transfer = (diff_transfer / lv_transfer * 100) if lv_transfer > 0 else 0
                longvan_comparison.append({
                    "tld": cur_item["tld"],
                    "field": "Giá chuyển đổi",
                    "plan_name": cur_item["tld"],
                    "old_price": prev_transfer,
                    "competitor_price": cur_transfer,
                    "competitor_diff": cur_transfer - prev_transfer,
                    "longvan_price": lv_transfer,
                    "diff_amount": diff_transfer,
                    "diff_pct": pct_transfer,
                    "status": "CHEAPER" if diff_transfer < 0 else ("EXPENSIVE" if diff_transfer > 0 else "EQUAL")
                })

            # Full 3-way comparison: Tổng chi phí 2 năm
            p_reg = float((last_items_map.get(tld, {}) or {}).get("register_price") or cur_reg or 0)
            p_ren = float((last_items_map.get(tld, {}) or {}).get("renew_price") or cur_renew or 0)
            prev_2yr = p_reg + p_ren
            if lv_2yr > 0 and cur_2yr > 0:
                diff_2yr = cur_2yr - lv_2yr
                pct_2yr = (diff_2yr / lv_2yr * 100) if lv_2yr > 0 else 0
                longvan_comparison.append({
                    "tld": cur_item["tld"],
                    "field": "Tổng chi phí 2 năm",
                    "plan_name": cur_item["tld"],
                    "old_price": prev_2yr,
                    "competitor_price": cur_2yr,
                    "competitor_diff": cur_2yr - prev_2yr,
                    "longvan_price": lv_2yr,
                    "diff_amount": diff_2yr,
                    "diff_pct": pct_2yr,
                    "status": "CHEAPER" if diff_2yr < 0 else ("EXPENSIVE" if diff_2yr > 0 else "EQUAL")
                })

        cheaper_than_lv = [c for c in longvan_comparison if c["status"] == "CHEAPER"]
        expensive_than_lv = [c for c in longvan_comparison if c["status"] == "EXPENSIVE"]
        equal_than_lv = [c for c in longvan_comparison if c["status"] == "EQUAL"]

        reg_comp = [c for c in longvan_comparison if c["field"] == "Giá đăng ký"]
        renew_comp = [c for c in longvan_comparison if c["field"] == "Giá gia hạn"]
        twoyr_comp = [c for c in longvan_comparison if c["field"] == "Tổng chi phí 2 năm"]

        # TLD Availability Analysis
        lv_tlds = set(longvan_items_map.keys())
        comp_tlds = set(current_items_map.keys())
        tld_availability = {
            "longvan_exclusive": sorted(list(lv_tlds - comp_tlds)),
            "competitor_exclusive": sorted(list(comp_tlds - lv_tlds)),
            "common": sorted(list(lv_tlds & comp_tlds)),
            "longvan_total": len(lv_tlds),
            "competitor_total": len(comp_tlds),
        }

        diff_result = {
            "provider_key": provider_key,
            "timestamp": get_vn_now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "total_items": len(current_items),
            "new_tlds": new_tlds,
            "price_changes": price_changes,
            "longvan_comparison": longvan_comparison,
            "longvan_summary": {
                "total_tlds_compared": len(set(c["tld"] for c in longvan_comparison)),
                "reg_cheaper_count": len([c for c in reg_comp if c["status"] == "CHEAPER"]),
                "reg_expensive_count": len([c for c in reg_comp if c["status"] == "EXPENSIVE"]),
                "reg_equal_count": len([c for c in reg_comp if c["status"] == "EQUAL"]),
                "renew_cheaper_count": len([c for c in renew_comp if c["status"] == "CHEAPER"]),
                "renew_expensive_count": len([c for c in renew_comp if c["status"] == "EXPENSIVE"]),
                "renew_equal_count": len([c for c in renew_comp if c["status"] == "EQUAL"]),
                "twoyr_cheaper_count": len([c for c in twoyr_comp if c["status"] == "CHEAPER"]),
                "twoyr_expensive_count": len([c for c in twoyr_comp if c["status"] == "EXPENSIVE"]),
                "twoyr_equal_count": len([c for c in twoyr_comp if c["status"] == "EQUAL"]),
                "cheaper_count": len(cheaper_than_lv),
                "expensive_count": len(expensive_than_lv),
                "equal_count": len(equal_than_lv),
                "cheaper_items": cheaper_than_lv,
                "expensive_items": expensive_than_lv
            },
            "tld_availability": tld_availability,
            "has_changes": bool(new_tlds or price_changes)
        }

        # Cập nhật snapshot mới (chỉ khi save=True)
        if save:
            new_snapshot = {
                "updated_at": diff_result["timestamp"],
                "url": url,
                "items": current_items
            }
            self.save_snapshot(provider_key, new_snapshot)
        return diff_result

    def compare_product_data(self, provider_key: str, product_type: str, current_items: list, url: str = "", save: bool = True) -> dict:
        """
        Dispatcher: Chuyển đến phương thức so sánh phù hợp (hiện tại chỉ hỗ trợ domain).
        """
        return self.compare_domain_data(provider_key, current_items, url, save=save)

    def compare_product_data_readonly(self, provider_key: str, product_type: str, current_items: list, url: str = "") -> dict:
        """
        Phiên bản read-only — KHÔNG ghi đè snapshot.
        """
        return self.compare_product_data(provider_key, product_type, current_items, url, save=False)

    def get_price_history(self, provider_key: str, limit: int = 10) -> list:
        """
        Trả về lịch sử snapshot (biến động giá theo thời gian) cho 1 provider.
        """
        history_dir = os.path.join(self.snapshot_dir, "history")
        if not os.path.exists(history_dir):
            return []

        import glob
        pattern = os.path.join(history_dir, f"{provider_key}_*.json")
        files = sorted(glob.glob(pattern), reverse=True)[:limit]

        history = []
        for fp in files:
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    snap = json.load(f)
                history.append({
                    "file": os.path.basename(fp),
                    "updated_at": snap.get("updated_at", ""),
                    "total_items": len(snap.get("items", [])),
                    "items": snap.get("items", [])
                })
            except Exception:
                pass
        return history
