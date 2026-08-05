import os
import sys
import json
import hashlib

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.auth_service import AuthService

def create_or_reset_admin(email="admin@longvan.net", password="admin", full_name="Admin Long Vân", role="admin"):
    auth = AuthService()
    pwd_hash = auth.hash_password(password)
    users_file = os.path.join(project_root, "storage", "users_db", "users.json")
    
    users = auth._load_users()
    existing = next((u for u in users if u["email"].lower() == email.lower()), None)
    
    now_str = auth.get_vn_now().strftime("%Y-%m-%d %H:%M:%S") if hasattr(auth, "get_vn_now") else "2026-08-05 14:16:00"
    
    if existing:
        existing["password_hash"] = pwd_hash
        existing["role"] = role
        existing["is_verified"] = True
        existing["full_name"] = full_name
        existing["updated_at"] = now_str
        print(f"[OK] Cập nhật thành công tài khoản {email} với mật khẩu '{password}'.")
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
        print(f"[OK] Đã tạo thành công tài khoản {email} với mật khẩu '{password}'.")
        
    auth._save_users(users)
    
    # Test login
    login_res = auth.login(email, password)
    print(f"[TEST LOGIN RESULT]: {login_res}")

if __name__ == "__main__":
    create_or_reset_admin()
