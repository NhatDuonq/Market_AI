import os
import json
import psycopg2
from datetime import datetime
from playwright.sync_api import sync_playwright

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = "market_ai"
DB_USER = "market"
DB_PASS = "abcxyz123@"

def save_to_db(records):
    if not records:
        return
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        
        inserted_count = 0
        for item in records:
            cur.execute("""
                SELECT new_data 
                FROM change_logs 
                WHERE provider = %s AND object_name = %s 
                ORDER BY created_at DESC 
                LIMIT 1;
            """, (item["provider"], item["object_name"]))
            
            row = cur.fetchone()
            last_price = row[0] if row else None
            
            if isinstance(last_price, str):
                last_price = last_price.strip('"')

            current_price = str(item["new_data"])

            if last_price is None:
                old_val = "0"
                should_save = True
            elif last_price != current_price:
                old_val = last_price
                should_save = True
            else:
                should_save = False

            if should_save:
                cur.execute("""
                    INSERT INTO change_logs (object_name, change_type, old_data, new_data, created_at, provider, url)
                    VALUES (%s, %s, %s::json, %s::json, %s, %s, %s)
                """, (
                    item["object_name"], item["change_type"],
                    json.dumps(old_val), json.dumps(current_price),
                    datetime.now(), item["provider"], item["url"]
                ))
                inserted_count += 1

        conn.commit()
        cur.close()
        conn.close()
        print(f"Vietnix: Quét xong. Có {inserted_count} sản phẩm thực sự thay đổi giá được lưu vào DB.")
    except Exception as e:
        print(f"Lỗi DB Vietnix: {e}")
