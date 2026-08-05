import os
import sys
import json
import hashlib
from datetime import datetime, timezone, timedelta

# Pure Python script - Zero external dependencies required!
VN_TZ = timezone(timedelta(hours=7))

def hash_password(password: str) -> str:
    salt = "LONGVAN_MARKET_AI_SALT_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def create_or_reset_admin(email="admin@longvan.net", password="admin", full_name="Admin Long Vân", role="admin"):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    users_dir = os.path.join(project_root, "storage", "users_db")
    os.makedirs(users_dir, exist_ok=True)
    users_file = os.path.join(users_dir, "users.json")
    
    users = []
    if os.path.exists(users_file):
        try:
            with open(users_file, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            users = []

    pwd_hash = hash_password(password)
    now_str = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    existing = next((u for u in users if u.get("email", "").lower() == email.lower()), None)
    
    if existing:
        existing["password_hash"] = pwd_hash
        existing["role"] = role
        existing["is_verified"] = True
        existing["full_name"] = full_name
        existing["updated_at"] = now_str
        print(f"[OK] Cập nhật thành công tài khoản '{email}' với mật khẩu '{password}'.")
    else:
        new_user = {
            "id": len(users) + 1,
            "email": email.lower(),
            "full_name": full_name,
            "password_hash": pwd_hash,
            "role": role,
            "is_verified": True,
            "created_at": now_str,
            "updated_at": now_str
        }
        users.append(new_user)
        print(f"[OK] Đã tạo mới thành công tài khoản '{email}' với mật khẩu '{password}'.")
        
    with open(users_file, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    
    print(f"[DONE] File users.json tại '{users_file}' đã được lưu thành công.")

if __name__ == "__main__":
    create_or_reset_admin()
