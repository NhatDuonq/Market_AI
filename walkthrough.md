# ✅ Triển khai Market AI Local — Hoàn tất

## Trạng thái: Tất cả 5 containers đang chạy

| Container | Image | Port | Status |
|---|---|---|---|
| **market-n8n-local** | n8nio/n8n:latest | `7000` → 5678 | ✅ Up |
| **market-adminer-local** | adminer | `7001` → 8080 | ✅ Up |
| **market-crawler-local** | market-ai-crawler | `7002` → 5000 | ✅ Up |
| **market-postgres-local** | postgres:16 | 5432 (internal) | ✅ Healthy |
| **market-redis-local** | redis:7-alpine | 6379 (internal) | ✅ Up |

---

## 🌐 Truy cập các dịch vụ

| Dịch vụ | URL | Tài khoản |
|---|---|---|
| **n8n** (Workflow) | [http://localhost:7000](http://localhost:7000) | admin / localdev123 |
| **Adminer** (Database GUI) | [http://localhost:7001](http://localhost:7001) | market_dev / localdev123 |
| **Crawler** (Webhook) | [http://localhost:7002/run-crawler](http://localhost:7002/run-crawler) | POST request |

### Đăng nhập Adminer
- System: **PostgreSQL**
- Server: **postgres**
- Username: **market_dev**
- Password: **localdev123**
- Database: **market_ai_dev**

---

## 📂 File đã tạo/sửa

### [NEW] [docker-compose.local.yml](file:///d:/market-ai/docker-compose.local.yml)
Docker Compose riêng cho local, port 7000/7001/7002, container name hậu tố `-local`, volume data riêng (`postgres-local`, `redis-local`, `n8n-local`).

### [MODIFY] [database.py](file:///d:/market-ai/crawler/common/database.py)
Refactor từ hard-code sang đọc biến môi trường (`DB_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`), giữ fallback giá trị production để không break VPS.

### [EXISTING] [.env.local](file:///d:/market-ai/.env.local)
Biến môi trường local (đã có sẵn từ trước).

### [EXISTING] [scripts/init_db.sql](file:///d:/market-ai/scripts/init_db.sql)
Tự động chạy khi PostgreSQL khởi tạo lần đầu (mount vào `/docker-entrypoint-initdb.d/`).

---

## 🔧 Các lệnh quản lý

```powershell
# Xem trạng thái
docker compose -f docker-compose.local.yml --env-file .env.local ps

# Xem log
docker compose -f docker-compose.local.yml --env-file .env.local logs -f

# Dừng hệ thống
docker compose -f docker-compose.local.yml --env-file .env.local down

# Khởi chạy lại
docker compose -f docker-compose.local.yml --env-file .env.local up -d

# Rebuild crawler sau khi sửa code
docker compose -f docker-compose.local.yml --env-file .env.local up -d --build crawler

# Test cào dữ liệu thủ công
curl -X POST http://localhost:7002/run-crawler
```
