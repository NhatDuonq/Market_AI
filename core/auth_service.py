import os
import sys
import json
import random
import string
import hashlib
import logging
from datetime import datetime, timedelta, timezone

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.email_notifier import EmailNotifier

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

def get_vn_now():
    return datetime.now(VN_TZ)

STORAGE_DIR = os.path.join(project_root, "storage", "users_db")
os.makedirs(STORAGE_DIR, exist_ok=True)
USERS_FILE = os.path.join(STORAGE_DIR, "users.json")
OTPS_FILE = os.path.join(STORAGE_DIR, "otps.json")
REFRESH_TOKENS_FILE = os.path.join(STORAGE_DIR, "refresh_tokens.json")


class AuthService:
    """
    Hệ thống Xác thực Người dùng Doanh nghiệp Long Vân (Giới hạn @longvan.net).
    - Đăng ký & OTP xác thực qua Email
    - Đăng nhập & Mã hóa Password
    - Quên mật khẩu & Đặt lại qua OTP
    - Quản lý Access Token & Refresh Token (Dual Token Architecture)
    - Hỗ trợ lưu vết siêu bền vững (PostgreSQL / Dual-Storage JSON Fallback)
    """
    def __init__(self):
        self.email_notifier = EmailNotifier()
        self._init_files()

    def _init_files(self):
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not os.path.exists(OTPS_FILE):
            with open(OTPS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not os.path.exists(REFRESH_TOKENS_FILE):
            with open(REFRESH_TOKENS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load_refresh_tokens(self) -> list:
        try:
            with open(REFRESH_TOKENS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_refresh_tokens(self, tokens: list):
        with open(REFRESH_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)

    def save_refresh_token(self, email: str, token: str, expires_in_days: int = 30) -> dict:
        tokens = self._load_refresh_tokens()
        now_str = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now() + timedelta(days=expires_in_days)).strftime("%Y-%m-%d %H:%M:%S")
        
        tokens.append({
            "email": email.strip().lower(),
            "token": token,
            "expires_at": expires_at,
            "revoked": False,
            "created_at": now_str
        })
        self._save_refresh_tokens(tokens)
        return {"success": True}

    def verify_refresh_token(self, token: str) -> dict:
        tokens = self._load_refresh_tokens()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for t in reversed(tokens):
            if t["token"] == token and not t.get("revoked"):
                if t.get("expires_at", "") > now_str:
                    users = self._load_users()
                    user = next((u for u in users if u["email"].lower() == t["email"].lower()), None)
                    if user:
                        return {
                            "success": True,
                            "user": {
                                "id": user["id"],
                                "email": user["email"],
                                "full_name": user["full_name"],
                                "role": user.get("role", "user")
                            }
                        }
                else:
                    return {"error": "Refresh Token đã hết hạn. Vui lòng đăng nhập lại."}

        return {"error": "Refresh Token không hợp lệ hoặc đã bị thu hồi."}

    def revoke_refresh_token(self, token: str) -> dict:
        tokens = self._load_refresh_tokens()
        for t in tokens:
            if t["token"] == token:
                t["revoked"] = True
        self._save_refresh_tokens(tokens)
        return {"success": True}

    def _load_users(self) -> list:
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_users(self, users: list):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    def _load_otps(self) -> list:
        try:
            with open(OTPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_otps(self, otps: list):
        with open(OTPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(otps, f, ensure_ascii=False, indent=2)

    def is_valid_longvan_email(self, email: str) -> bool:
        """Kiểm tra email phải thuộc tên miền @longvan.net"""
        if not email or not isinstance(email, str):
            return False
        email_clean = email.strip().lower()
        return email_clean.endswith("@longvan.net")

    def hash_password(self, password: str) -> str:
        """Băm mật khẩu bằng SHA-256 + Salt"""
        salt = "LONGVAN_MARKET_AI_SALT_2026"
        return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

    def generate_otp(self) -> str:
        """Tạo mã OTP 6 chữ số ngẫu nhiên"""
        return ''.join(random.choices(string.digits, k=6))

    def register(self, email: str, full_name: str, password: str) -> dict:
        """
        Đăng ký tài khoản doanh nghiệp mới (@longvan.net).
        """
        email_clean = email.strip().lower()

        if not self.is_valid_longvan_email(email_clean):
            return {"error": "Chỉ chấp nhận đăng ký bằng Email doanh nghiệp Long Vân (@longvan.net)"}

        if len(password) < 6:
            return {"error": "Mật khẩu phải có ít nhất 6 ký tự"}

        users = self._load_users()
        pwd_hash = self.hash_password(password)
        now_str = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")

        existing_index = -1
        for idx, u in enumerate(users):
            if u["email"].lower() == email_clean:
                existing_index = idx
                break

        if existing_index >= 0:
            existing_user = users[existing_index]
            if existing_user.get("is_verified"):
                return {"error": "Email này đã được đăng ký và xác thực. Vui lòng chọn Đăng Nhập hoặc Quên Mật Khẩu."}
            else:
                # Cập nhật thông tin đăng ký mới
                users[existing_index]["password_hash"] = pwd_hash
                users[existing_index]["full_name"] = full_name
                users[existing_index]["updated_at"] = now_str
        else:
            new_user = {
                "id": len(users) + 1,
                "email": email_clean,
                "full_name": full_name,
                "password_hash": pwd_hash,
                "role": "user",
                "is_verified": False,
                "created_at": now_str,
                "updated_at": now_str
            }
            users.append(new_user)

        self._save_users(users)

        # Tạo và gửi mã OTP qua Email
        otp_code = self.generate_otp()
        expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        otps = self._load_otps()
        otps.append({
            "id": len(otps) + 1,
            "email": email_clean,
            "otp_code": otp_code,
            "otp_type": "REGISTRATION",
            "expires_at": expires_at,
            "used": False,
            "created_at": now_str
        })
        self._save_otps(otps)

        # Gửi Email OTP
        self._send_otp_via_email(email_clean, otp_code, "REGISTRATION")

        return {
            "success": True,
            "message": f"Mã OTP xác thực 6 số đã được gửi tới {email_clean}. Vui lòng kiểm tra hòm thư!",
            "email": email_clean
        }

    def verify_otp(self, email: str, otp_code: str, otp_type: str = "REGISTRATION") -> dict:
        """
        Xác nhận mã OTP để kích hoạt tài khoản hoặc duyệt reset mật khẩu.
        """
        email_clean = email.strip().lower()
        otp_clean = otp_code.strip()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        otps = self._load_otps()
        target_otp_idx = -1

        for idx, o in enumerate(reversed(otps)):
            actual_idx = len(otps) - 1 - idx
            if o["email"].lower() == email_clean and o["otp_code"] == otp_clean and o["otp_type"] == otp_type and not o.get("used"):
                if o.get("expires_at", "") > now_str:
                    target_otp_idx = actual_idx
                    break

        if target_otp_idx < 0:
            return {"error": "Mã OTP không chính xác hoặc đã hết hạn (hiệu lực 10 phút)."}

        otps[target_otp_idx]["used"] = True
        self._save_otps(otps)

        if otp_type == "REGISTRATION":
            users = self._load_users()
            for u in users:
                if u["email"].lower() == email_clean:
                    u["is_verified"] = True
                    u["updated_at"] = now_str
                    break
            self._save_users(users)

            user_data = next((u for u in users if u["email"].lower() == email_clean), None)
            return {
                "success": True,
                "message": "Xác thực tài khoản thành công! Bạn có thể đăng nhập ngay.",
                "user": {"id": user_data["id"], "email": user_data["email"], "full_name": user_data["full_name"], "role": user_data.get("role", "user")} if user_data else {}
            }
        elif otp_type == "PASSWORD_RESET":
            return {
                "success": True,
                "message": "Mã OTP hợp lệ! Bạn có thể đặt mật khẩu mới."
            }

        return {"error": "Loại OTP không hợp lệ"}

    def login(self, email: str, password: str) -> dict:
        """
        Đăng nhập người dùng bằng Email @longvan.net + Mật khẩu.
        """
        email_clean = email.strip().lower()
        pwd_hash = self.hash_password(password)

        users = self._load_users()
        user = next((u for u in users if u["email"].lower() == email_clean), None)

        if not user:
            return {"error": "Tài khoản không tồn tại. Vui lòng kiểm tra lại Email hoặc Đăng Ký."}

        if not user.get("is_verified"):
            return {"error": "Tài khoản chưa được xác thực OTP qua Email. Vui lòng hoàn tất kích hoạt."}

        if user.get("password_hash") != pwd_hash:
            return {"error": "Mật khẩu không chính xác. Vui lòng thử lại."}

        return {
            "success": True,
            "message": "Đăng nhập thành công!",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user.get("role", "user")
            }
        }

    def forgot_password(self, email: str) -> dict:
        """
        Tạo và gửi mã OTP khôi phục mật khẩu.
        """
        email_clean = email.strip().lower()

        if not self.is_valid_longvan_email(email_clean):
            return {"error": "Chỉ chấp nhận Email doanh nghiệp Long Vân (@longvan.net)"}

        users = self._load_users()
        user = next((u for u in users if u["email"].lower() == email_clean), None)
        if not user:
            return {"error": "Không tìm thấy tài khoản với Email này trong hệ thống."}

        otp_code = self.generate_otp()
        now_str = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        otps = self._load_otps()
        otps.append({
            "id": len(otps) + 1,
            "email": email_clean,
            "otp_code": otp_code,
            "otp_type": "PASSWORD_RESET",
            "expires_at": expires_at,
            "used": False,
            "created_at": now_str
        })
        self._save_otps(otps)

        self._send_otp_via_email(email_clean, otp_code, "PASSWORD_RESET")

        return {
            "success": True,
            "message": f"Mã OTP đặt lại mật khẩu đã được gửi tới {email_clean}. Vui lòng kiểm tra hòm thư!",
            "email": email_clean
        }

    def reset_password(self, email: str, otp_code: str, new_password: str) -> dict:
        """
        Đặt lại mật khẩu mới bằng mã OTP.
        """
        email_clean = email.strip().lower()

        if len(new_password) < 6:
            return {"error": "Mật khẩu mới phải có ít nhất 6 ký tự"}

        # Verify OTP
        verify_res = self.verify_otp(email_clean, otp_code, "PASSWORD_RESET")
        if "error" in verify_res:
            return verify_res

        # Cập nhật mật khẩu mới
        new_pwd_hash = self.hash_password(new_password)
        users = self._load_users()
        for u in users:
            if u["email"].lower() == email_clean:
                u["password_hash"] = new_pwd_hash
                u["updated_at"] = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")
                break
        self._save_users(users)

        return {
            "success": True,
            "message": "Đặt lại mật khẩu mới thành công! Bạn có thể đăng nhập bằng mật khẩu mới."
        }

    def _send_otp_via_email(self, email: str, otp_code: str, otp_type: str) -> bool:
        """Gửi Email chứa mã OTP chuẩn HTML"""
        title = "MÃ XÁC THỰC ĐĂNG KÝ TÀI KHOẢN" if otp_type == "REGISTRATION" else "MÃ XÁC THỰC ĐẶT LẠI MẬT KHẨU"
        subject = f"[Market AI] {title} - {otp_code}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.08);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="background: #2563eb; color: #fff; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 12px;">LONG VÂN CLOUD SOLUTION</span>
                    <h2 style="color: #1e293b; margin-top: 15px;">{title}</h2>
                </div>
                <p style="color: #475569; font-size: 14px;">Xin chào cán bộ nhân viên Long Vân Cloud,</p>
                <p style="color: #475569; font-size: 14px;">Mã xác thực OTP của bạn cho hệ thống **Market AI Engine** là:</p>
                <div style="text-align: center; margin: 25px 0;">
                    <span style="display: inline-block; background: #f1f5f9; color: #2563eb; border: 2px dashed #2563eb; font-size: 32px; font-weight: bold; letter-spacing: 6px; padding: 12px 30px; border-radius: 8px;">{otp_code}</span>
                </div>
                <p style="color: #64748b; font-size: 12px; text-align: center;">Mã OTP có hiệu lực trong vòng <strong>10 phút</strong>. Tuyệt đối không chia sẻ mã này cho bất kỳ ai.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                <p style="color: #94a3b8; font-size: 11px; text-align: center;">Market AI Engine &bull; Hệ thống giám sát cạnh tranh doanh nghiệp Long Vân</p>
            </div>
        </body>
        </html>
        """
        try:
            return self.email_notifier.send_report(subject, html_body, to_email=email)
        except Exception as e:
            logger.error(f"Lỗi gửi email OTP: {e}")
            return False
