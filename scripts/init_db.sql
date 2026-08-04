-- =============================================
-- Market AI - Database Initialization Script
-- =============================================

-- 1. Bảng quản lý URL toàn bộ trang đối thủ
CREATE TABLE IF NOT EXISTS website_pages (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    page_type VARCHAR(50) DEFAULT 'other',
    status VARCHAR(20) DEFAULT 'pending',
    last_crawled_at TIMESTAMP
);

-- 2. Bảng nhật ký biến động (Giá, Nội dung, Sản phẩm mới)
CREATE TABLE IF NOT EXISTS change_logs (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    object_type VARCHAR(50),
    object_name TEXT,
    change_type VARCHAR(50),
    old_data JSONB,
    new_data JSONB,
    description TEXT,
    url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Bảng snapshot lưu trữ nội dung HTML trang web
CREATE TABLE IF NOT EXISTS website_snapshots (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT,
    html TEXT,
    hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Bảng lưu Bình luận & Đánh giá của khách hàng đối thủ
CREATE TABLE IF NOT EXISTS customer_reviews (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    url TEXT NOT NULL,
    author_name VARCHAR(200),
    rating INT,
    comment_text TEXT,
    reply_text TEXT,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index tối ưu truy vấn
CREATE INDEX IF NOT EXISTS idx_change_logs_provider ON change_logs (provider, object_name);
CREATE INDEX IF NOT EXISTS idx_change_logs_created ON change_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_website_pages_status ON website_pages (provider, status);
CREATE INDEX IF NOT EXISTS idx_customer_reviews_provider ON customer_reviews (provider);
