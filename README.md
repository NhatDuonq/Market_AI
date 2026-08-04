# Market AI - Competitive Market Intelligence & Price Tracker

**Market AI** là hệ thống tự động theo dõi, cào dữ liệu (Web Scraping bằng Playwright) và phân tích biến động giá tên miền giữa **Long Vân (Benchmark)** và các đối thủ cạnh tranh (**Mắt Bão**, **PA Việt Nam**). Hệ thống tích hợp **Gemini AI** để đưa ra phân tích chiến lược và hỗ trợ báo cáo đa kênh qua **Telegram Bot** và **Email**.

---

## 📌 Tính năng cốt lõi

1. **Cào dữ liệu tự động (Web Scraping)**: Sử dụng Playwright giả lập trình duyệt, cào bảng giá Tên miền và tự động chụp ảnh màn hình (Screenshot) làm bằng chứng đối soát dữ liệu.
2. **Lõi Phân Tích & Đối So (Diff Engine)**: 
   - So sánh Giá đăng ký năm 1, Giá gia hạn, Giá chuyển đổi, và **Tổng chi phí 2 năm đầu**.
   - Phân tích **Độ phủ TLD (TLD Availability)**: Phát hiện TLD độc quyền của Long Vân và TLD mà Long Vân đang bỏ lỡ.
3. **Phân Tích AI (Gemini AI)**: Tự động phân tích ý đồ chiến lược của đối thủ và đưa ra hướng đi tiếp theo (Actionable Insights) cho team Long Vân.
4. **Báo Cáo Đa Kênh (Multi-channel Alerts)**: Đẩy thông tin biến động + khuyên nghị AI + Screenshot qua **Telegram Bot** và **Email (HTML)**.
5. **Giao Diện Dashboard (Streamlit)**: Dark UI cao cấp, có Dropdown chọn đối thủ, hiển thị trực quan biểu đồ, bảng dữ liệu 3 chiều và thư viện screenshot.
6. **Sẵn sàng đóng gói CI/CD & Docker**: Tối ưu hóa Dockerfile nhẹ, hỗ trợ deployment tự động lên VPS qua GitHub Actions.

---

## 🏗 Kiến trúc Docker & Cổng kết nối

Hệ thống được đóng gói thành 2 dịch vụ chính chạy trong Docker:

| Service | Công nghệ | Port | Mô tả |
| :--- | :--- | :--- | :--- |
| **market-scheduler** | Python + APScheduler | `5001` | Lên lịch chạy cào dữ liệu tự động định kỳ (mặc định 30 phút/lần) và cung cấp REST API trigger. |
| **market-dashboard** | Streamlit | `8501` | Giao diện Quản trị & So sánh giá trực quan qua Web. |

---

## 📂 Thư mục Dự án

```text
market-ai/
├── Dockerfile                  # Production Dockerfile tối ưu cho Playwright Python 3.12
├── docker-compose.yml          # Đóng gói Scheduler và Dashboard
├── requirements.txt            # Thư viện dependencies
├── main.py                     # CLI điều phối cào dữ liệu chính
├── scheduler.py                # Service lên lịch chạy định kỳ 24/7
├── config/
│   └── crawler_targets.json    # Cấu hình bật/tắt các mục tiêu cào
├── core/
│   ├── base_provider.py        # Lớp cơ sở Playwright browser anti-detect
│   ├── diff_engine.py          # Lõi so sánh giá 3-way & TLD availability
│   ├── ai_analyzer.py          # Module phân tích Gemini AI + Cache
│   ├── telegram_notifier.py    # Gửi báo cáo qua Telegram
│   └── email_notifier.py       # Gửi báo cáo HTML qua Email SMTP
├── providers/                  # Module cào dữ liệu từng bên
│   ├── longvan/                # Benchmark provider (Long Vân)
│   ├── matbao/                 # Đối thủ Mắt Bão
│   └── pavietnam/              # Đối thủ PA Việt Nam
├── dashboard/
│   └── app.py                  # Giao diện Streamlit Dashboard
├── storage/                    # Lưu trữ dữ liệu lâu dài (Volume mount)
│   ├── snapshots/              # Snapshots JSON & Lịch sử biến động
│   ├── screenshots/            # Ảnh chụp màn hình giao diện đối thủ
│   └── ai_cache/               # Cache kết quả AI
└── .github/workflows/
    └── deploy.yml              # Quy trình CI/CD tự động (Test + Deploy VPS)
```

---

## 🚀 Hướng Dẫn Vận Hành Tại Local

### 1. Cài đặt môi trường
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Chạy thủ công cào dữ liệu
```bash
python main.py --all
```

### 3. Mở Dashboard Streamlit
```bash
streamlit run dashboard/app.py
```
*(Truy cập: `http://localhost:8501`, Mật khẩu mặc định: `123456`)*

---

## 🐳 Hướng Dẫn Đóng Gói Docker & Deploy Lên VPS

### 1. Khởi chạy bằng Docker Compose trên VPS
```bash
# Clone dự án về VPS
git clone <your-repo-url> /var/www/market-ai
cd /var/www/market-ai

# Tạo file .env từ mẫu và cấu hình API Key
cp .env.example .env

# Khởi chạy Docker containers
docker compose up -d --build
```

### 2. Quản lý Containers
```bash
# Xem danh sách container đang chạy
docker compose ps

# Xem log thời gian thực
docker compose logs -f

# Rebuild container khi có code mới
docker compose up -d --build
```

---

## ⚡ Hướng Dẫn Thiết Lập CI/CD Bằng GitHub Actions

File workflow đã được cấu hình sẵn tại `.github/workflows/deploy.yml`. Khi bạn `git push` code lên nhánh `main` hoặc `master`, GitHub Actions sẽ:
1. Tự động chạy bộ kiểm thử (`pytest tests/`).
2. Nếu test PASS -> Tự động SSH vào VPS, kéo code mới và chạy `docker compose up -d --build`.

### Cần cấu hình các Secrets sau trên GitHub Repository:
Vào GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions** -> Thêm các **Repository secrets**:

| Secret Name | Mô tả | Ví dụ |
| :--- | :--- | :--- |
| `VPS_HOST` | Địa chỉ IP / Domain của VPS | `103.95.159.37` |
| `VPS_USERNAME` | Tài khoản SSH VPS | `root` |
| `VPS_SSH_KEY` | Khóa SSH Private Key (`cat ~/.ssh/id_rsa`) | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `VPS_PORT` | Cổng SSH (Mặc định 22) | `22` |
| `VPS_PROJECT_PATH` | Đường dẫn dự án trên VPS | `/var/www/market-ai` |
