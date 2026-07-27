import hashlib
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# 1. Cấu hình kết nối Database (market_ai)
DB_CONFIG = {
    "host": "market-postgres", # Tên container hoặc localhost tùy setup của bạn
    "database": "market_ai",
    "user": "market",
    "password": "abcxyz123@" # Thay bằng mật khẩu của bạn
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def crawl_inet_homepage():
    print("🚀 [Crawler] Starting iNET homepage crawler...")
    
    with sync_playwright() as p:
        # Khởi chạy trình duyệt ẩn danh
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        url = "https://inet.vn"
        page.goto(url, wait_until="networkidle")
        
        # Lấy các thông tin cần thiết
        html_content = page.content()
        title = page.title()
        
        # Dùng BeautifulSoup để bóc tách text sạch (loại bỏ script/style rác)
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        clean_text = soup.get_text(separator=' ')
        
        # Tạo mã hóa MD5 hash dựa trên text sạch để nhận diện thay đổi nội dung
        text_hash = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
        
        browser.close()
        
        return {
            "provider": "iNET",
            "url": url,
            "title": title,
            "html": html_content,
            "content": clean_text,
            "hash": text_hash
        }

def process_change_detection(data):
    conn = get_db_connection()
    # Dùng RealDictCursor để khi fetch data trả về dạng dict cho dễ xử lý
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Truy vấn lấy snapshot gần nhất của iNET để so sánh
        query_last_snapshot = """
            SELECT hash, html, content FROM website_snapshots 
            WHERE provider = %s 
            ORDER BY created_at DESC LIMIT 1;
        """
        cur.execute(query_last_snapshot, (data["provider"],))
        last_snapshot = cur.fetchone()
        
        # Mặc định giả định là cần lưu snapshot mới
        should_save_snapshot = False
        
        if not last_snapshot:
            # Trường hợp hệ thống chạy lần đầu tiên, chưa có dữ liệu cũ
            print("ℹ️ No previous snapshot found. Saving initial snapshot...")
            should_save_snapshot = True
            
        else:
            old_hash = last_snapshot["hash"]
            new_hash = data["hash"]
            
            if old_hash == new_hash:
                # Trùng hash = Không có thay đổi gì trên website
                print(f"✅ [No Change] Hash matches ({new_hash}). Skipping log and storage.")
            else:
                # Khác hash = Website đã bị thay đổi!
                print(f"🚨 [CHANGE DETECTED] Old Hash: {old_hash} | New Hash: {new_hash}")
                should_save_snapshot = True
                
                # Tạo bản ghi log thay đổi vào bảng change_logs thông minh vừa tạo
                insert_log_query = """
                    INSERT INTO change_logs (
                        provider, object_type, object_name, change_type, old_data, new_data, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                """
                
                # Đóng gói dữ liệu cũ và mới vào JSON
                old_data_json = json.dumps({"hash": old_coords if (old_coords := old_hash) else ""}) 
                new_data_json = json.dumps({"hash": new_hash})
                description = f"Phát hiện thay đổi giao diện/nội dung trên trang chủ iNET. Chiều dài text hiện tại: {len(data['content'])} ký tự."
                
                cur.execute(insert_log_query, (
                    data["provider"],
                    "homepage",
                    "iNET Homepage",
                    "content_changed",
                    old_data_json,
                    new_data_json,
                    description
                ))
                print("💾 Change log successfully saved to change_logs table!")

        # 2. Nếu có thay đổi hoặc chạy lần đầu, tiến hành lưu snapshot mới làm mốc lịch sử
        if should_save_snapshot:
            insert_snapshot_query = """
                INSERT INTO website_snapshots (provider, url, title, content, html, hash)
                VALUES (%s, %s, %s, %s, %s, %s);
            """
            cur.execute(insert_snapshot_query, (
                data["provider"],
                data["url"],
                data["title"],
                data["content"],
                data["html"],
                data["hash"]
            ))
            conn.commit()
            print("💾 New snapshot saved to website_snapshots table!")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during change detection: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    # Chạy quy trình
    crawled_data = crawl_inet_homepage()
    process_change_detection(crawled_data)
