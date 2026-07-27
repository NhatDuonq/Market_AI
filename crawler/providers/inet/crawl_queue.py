import hashlib
import json
import psycopg2
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

DB_CONFIG = {
    "host": "market-postgres",
    "database": "market_ai",
    "user": "market",
    "password": "abcxyz123@"  # <-- Nhớ thay mật khẩu chuẩn của bạn vào đây
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def crawl_next_page():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Lấy ra 1 URL đang chờ xử lý (pending)
    cur.execute("""
        SELECT id, url, page_type 
        FROM website_pages 
        WHERE provider_name = 'inet' AND status = 'pending'
        LIMIT 1 FOR UPDATE SKIP LOCKED;
    """)
    row = cur.fetchone()
    
    if not row:
        cur.close()
        conn.close()
        return False  # Hết dữ liệu trong queue
        
    page_id, url, page_type = row
    print(f"🚀 [Queue Worker] Processing URL ID {page_id}: {url} ({page_type})")
    
    # Cập nhật trạng thái tạm thời để tránh container khác tranh chấp
    cur.execute("UPDATE website_pages SET status = 'processing' WHERE id = %s;", (page_id,))
    conn.commit()
    
    try:
        # 2. Dùng Playwright để cào nội dung trang
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            html_content = page.content()
            browser.close()
            
        # 3. Tính mã toán học hash MD5
        new_hash = hashlib.md5(html_content.encode('utf-8')).hexdigest()
        
        # 4. Lấy dữ liệu hash cũ nhất dựa trên created_at từ website_snapshots
        cur.execute("""
            SELECT hash FROM website_snapshots 
            WHERE url = %s 
            ORDER BY created_at DESC LIMIT 1;
        """, (url,))
        old_row = cur.fetchone()
        old_hash = old_row[0] if old_row else None
        
        # 5. So sánh đối chiếu logic Change Detection
        if old_hash != new_hash:
            print(f"🚨 [CHANGE DETECTED] URL: {url} | Old: {old_hash} -> New: {new_hash}")
            
            old_data_json = json.dumps({"hash": old_hash})
            new_data_json = json.dumps({"hash": new_hash})
            description_text = f"Phát hiện thay đổi cấu trúc mã nguồn trang. Loại trang: {page_type}"
            
            # INSERT chuẩn xác vào bảng change_logs
            cur.execute("""
                INSERT INTO change_logs (provider, object_type, object_name, change_type, old_data, new_data, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, ("inet", "website_page", url, "snapshot_changed", old_data_json, new_data_json, description_text))
            
            # INSERT chuẩn xác vào bảng website_snapshots
            cur.execute("""
                INSERT INTO website_snapshots (provider, url, title, content, html, hash)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, ("inet", url, f"iNET - {page_type}", f"Snapshot data for {page_type}", html_content, new_hash))
        else:
            print(f"✅ [No Change] Hash matches for {url}. Skipping database log.")
            
        # 6. Chuyển trạng thái sang hoàn thành (completed)
        cur.execute("""
            UPDATE website_pages 
            SET status = 'completed', last_crawled_at = %s 
            WHERE id = %s;
        """, (datetime.now(), page_id))
        conn.commit()
        
    except Exception as e:
        print(f"❌ Error processing URL ID {page_id}: {e}")
        conn.rollback()
        cur.execute("UPDATE website_pages SET status = 'failed' WHERE id = %s;", (page_id,))
        conn.commit()
        
    finally:
        cur.close()
        conn.close()
        
    return True

if __name__ == "__main__":
    print("🤖 Starting Market AI Worker Loop...")
    has_more = True
    while has_more:
        has_more = crawl_next_page()
        if has_more:
            # Nghỉ 2 giây giữa các lần cào để tránh bị firewall đối thủ block IP (Antiban rate limit)
            time.sleep(2) 
            
    print("🏁 All URLs in queue have been processed successfully!")
