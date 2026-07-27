import xml.etree.ElementTree as ET
import requests
import psycopg2
from datetime import datetime

DB_CONFIG = {
    "host": "market-postgres",
    "database": "market_ai",
    "user": "market",
    "password": "abcxyz123@"  # <-- Thay mật khẩu chuẩn của bạn vào đây
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def discover_all_urls():
    # URL sitemap chính của iNET (hoặc đối thủ khác tương tự)
    sitemap_url = "https://inet.vn/sitemap.xml"
    print(f"🌐 Fetching sitemap from: {sitemap_url}")
    
    try:
        response = requests.get(sitemap_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch sitemap. Status code: {response.status_code}")
            return
            
        # Phân tích cú pháp XML để rút ra toàn bộ URLs
        root = ET.fromstring(response.content)
        # Khai báo namespace mặc định của sitemap
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        urls = []
        for url_tag in root.findall('.//ns:loc', namespaces):
            urls.append(url_tag.text)
            
        print(f"🔍 Found {len(urls)} total URLs from sitemap.")
        
        # Lưu toàn bộ URL vào Database
        conn = get_db_connection()
        cur = conn.cursor()
        
        inserted_count = 0
        for url in urls:
            try:
                # Xác định sơ bộ loại trang dựa trên URL để sau này dễ bóc tách
                page_type = "other"
                if "vps" in url or "cloud-server" in url:
                    page_type = "vps"
                elif "hosting" in url:
                    page_type = "hosting"
                elif "ten-mien" in url or "domain" in url:
                    page_type = "domain"
                
                cur.execute("""
                    INSERT INTO website_pages (provider_name, url, page_type, status)
                    VALUES (%s, %s, %s, 'pending')
                    ON CONFLICT (url) DO NOTHING;
                """, ("inet", url, page_type))
                inserted_count += cur.rowcount
            except Exception as e:
                print(f"⚠ Error inserting URL {url}: {e}")
                
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"💾 Successfully integrated {inserted_count} NEW URLs into database queue!")
        
    except Exception as e:
        print(f"❌ Error during sitemap discovery: {e}")

if __name__ == "__main__":
    discover_all_urls()
