import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Module gửi báo cáo phân tích thị trường qua Email (SMTP).
    Hỗ trợ gửi HTML đẹp mắt kèm hình ảnh đính kèm.
    """
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", self.smtp_user)
        self.to_emails = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]

    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.to_emails)

    def send_report(self, subject: str, html_body: str, screenshot_paths: list = None, to_email: str = None) -> bool:
        """
        Gửi báo cáo HTML kèm ảnh chụp màn hình qua Email.
        """
        recipients = [to_email.strip()] if to_email else [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]
        
        if not self.smtp_user or not self.smtp_password or not recipients:
            logger.warning("[EmailNotifier] Chưa cấu hình SMTP hoặc thiếu Email người nhận. Bỏ qua gửi email.")
            return False

        try:
            msg = MIMEMultipart("related")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(recipients)

            # Attach HTML body
            html_part = MIMEText(html_body, "html", "utf-8")
            msg.attach(html_part)

            # Attach screenshots
            if screenshot_paths:
                for idx, path in enumerate(screenshot_paths):
                    if path and os.path.exists(path):
                        try:
                            with open(path, 'rb') as img_file:
                                img = MIMEImage(img_file.read())
                                img.add_header('Content-ID', f'<screenshot_{idx}>')
                                img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                                msg.attach(img)
                        except Exception as e:
                            logger.warning(f"Không thể đính kèm ảnh {path}: {e}")

            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, recipients, msg.as_string())

            logger.info(f"[EmailNotifier] Đã gửi email đến {', '.join(recipients)}")
            return True
        except Exception as e:
            logger.error(f"[EmailNotifier] Lỗi gửi email: {e}")
            return False

    def format_domain_report_html(self, provider_name: str, diff_data: dict, ai_analysis: str = "") -> str:
        """
        Tạo HTML Email báo cáo sang trọng, chuẩn Email Client (Gmail/Outlook), độ tương phản cao, dễ đọc.
        """
        timestamp = diff_data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        url = diff_data.get("url", "")
        total = diff_data.get("total_items", 0)

        # Extraction from diff_data
        longvan_summary = diff_data.get("longvan_summary", {})
        longvan_comp = diff_data.get("longvan_comparison", [])
        tld_avail = diff_data.get("tld_availability", {})
        price_changes = diff_data.get("price_changes", [])
        new_tlds = diff_data.get("new_tlds", [])

        reg_comp = [c for c in longvan_comp if c.get("field") == "Giá đăng ký"]
        renew_comp = [c for c in longvan_comp if c.get("field") == "Giá gia hạn"]
        twoyr_comp = [c for c in longvan_comp if c.get("field") == "Tổng chi phí 2 năm"]

        reg_cheaper = len([c for c in reg_comp if c.get("status") == "CHEAPER"])
        renew_cheaper = len([c for c in renew_comp if c.get("status") == "CHEAPER"])
        twoyr_cheaper = len([c for c in twoyr_comp if c.get("status") == "CHEAPER"])

        twoyr_expensive = len([c for c in twoyr_comp if c.get("status") == "EXPENSIVE"])

        # Truncate TLD availability
        lv_exclusive = tld_avail.get("longvan_exclusive", [])
        comp_exclusive = tld_avail.get("competitor_exclusive", [])

        comp_ex_str = ", ".join(comp_exclusive[:20])
        if len(comp_exclusive) > 20:
            comp_ex_str += f" ... và <strong>{len(comp_exclusive) - 20} TLD khác</strong>"

        lv_ex_str = ", ".join(lv_exclusive[:20]) if lv_exclusive else "Không có"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Market AI Report</title>
        </head>
        <body style="margin:0; padding:20px; background-color:#f1f5f9; font-family:'Segoe UI', Arial, sans-serif; color:#334155;">
            <table align="center" width="650" border="0" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08); margin:0 auto;">
                
                <!-- HEADER -->
                <tr>
                    <td style="background-color:#1e293b; padding:28px 32px; text-align:left;">
                        <table width="100%" border="0" cellpadding="0" cellspacing="0">
                            <tr>
                                <td>
                                    <span style="background-color:#3b82f6; color:#ffffff; font-size:11px; font-weight:700; padding:4px 10px; border-radius:4px; text-transform:uppercase; letter-spacing:0.5px;">MARKET AI ENGINE</span>
                                    <h1 style="color:#ffffff; font-size:22px; font-weight:700; margin:10px 0 4px 0;">Báo Cáo Cạnh Tranh Tên Miền</h1>
                                    <p style="color:#94a3b8; font-size:13px; margin:0;">Đối thủ: <strong style="color:#f8fafc;">{provider_name.upper()}</strong> | Quét lúc: {timestamp}</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- CONTENT -->
                <tr>
                    <td style="padding:28px 32px;">

                        <!-- KPI SUMMARY CARDS -->
                        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                            <tr>
                                <td width="31%" style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; text-align:center;">
                                    <div style="font-size:24px; font-weight:800; color:#2563eb;">{total}</div>
                                    <div style="font-size:12px; font-weight:600; color:#64748b; margin-top:4px;">Tổng TLD cào được</div>
                                </td>
                                <td width="3.5%"></td>
                                <td width="31%" style="background-color:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:16px; text-align:center;">
                                    <div style="font-size:24px; font-weight:800; color:#dc2626;">{twoyr_cheaper} TLD</div>
                                    <div style="font-size:12px; font-weight:600; color:#991b1b; margin-top:4px;">Đối thủ GIÁ THẤP HƠN (Tổng 2 năm)</div>
                                </td>
                                <td width="3.5%"></td>
                                <td width="31%" style="background-color:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:16px; text-align:center;">
                                    <div style="font-size:24px; font-weight:800; color:#16a34a;">{twoyr_expensive} TLD</div>
                                    <div style="font-size:12px; font-weight:600; color:#166534; margin-top:4px;">Long Vân GIÁ THẤP HƠN (Tổng 2 năm)</div>
                                </td>
                            </tr>
                        </table>

                        <!-- TLD AVAILABILITY -->
                        <div style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:18px 20px; margin-bottom:24px;">
                            <h3 style="color:#0f172a; font-size:15px; margin:0 0 10px 0;">🔍 Phân Tích Độ Phủ TLD</h3>
                            <p style="margin:0 0 8px 0; font-size:13px; line-height:1.5;">
                                <strong style="color:#16a34a;">✅ Lợi thế Long Vân:</strong> {lv_ex_str}
                            </p>
                            <p style="margin:0; font-size:13px; line-height:1.5; color:#475569;">
                                <strong style="color:#dc2626;">⚠️ Thị phần đối thủ có (LV chưa có):</strong> {comp_ex_str}
                            </p>
                        </div>

                        <!-- DOMAIN PRICE COMPARISON TABLE -->
                        <h3 style="color:#0f172a; font-size:16px; font-weight:700; margin:0 0 12px 0; border-bottom:2px solid #e2e8f0; padding-bottom:8px;">
                            ⚔️ So Sánh Chi Tiết Các TLD Chính (Long Vân vs {provider_name.upper()})
                        </h3>

                        <table width="100%" border="0" cellpadding="8" cellspacing="0" style="border-collapse:collapse; font-size:13px; margin-bottom:24px;">
                            <thead>
                                <tr style="background-color:#f1f5f9; color:#334155; text-align:left;">
                                    <th style="padding:10px; border-bottom:2px solid #cbd5e1;">TLD</th>
                                    <th style="padding:10px; border-bottom:2px solid #cbd5e1;">Hạng mục</th>
                                    <th style="padding:10px; border-bottom:2px solid #cbd5e1;">Giá Đối Thủ</th>
                                    <th style="padding:10px; border-bottom:2px solid #cbd5e1;">Giá Long Vân</th>
                                    <th style="padding:10px; border-bottom:2px solid #cbd5e1;">Vị Thế</th>
                                </tr>
                            </thead>
                            <tbody>
        """

        # Populate top comparison rows (specifically .vn TLDs)
        vn_tlds = [".vn", ".com.vn", ".net.vn", ".edu.vn", ".health.vn", ".pro.vn", ".id.vn", ".name.vn"]
        filtered_comp = [c for c in twoyr_comp if c.get("tld") in vn_tlds]
        if not filtered_comp:
            filtered_comp = twoyr_comp[:10]

        for idx, row in enumerate(filtered_comp):
            bg = "#ffffff" if idx % 2 == 0 else "#f8fafc"
            status = row.get("status")
            status_html = '<span style="color:#dc2626; font-weight:700;">⚠️ Đối thủ giá thấp hơn</span>' if status == "CHEAPER" \
                else ('<span style="color:#16a34a; font-weight:700;">✅ LV giá thấp hơn</span>' if status == "EXPENSIVE" else '<span style="color:#64748b;">⚖️ Bằng giá</span>')

            comp_p = row.get("competitor_price", 0)
            lv_p = row.get("longvan_price", 0)

            html += f"""
                                <tr style="background-color:{bg}; border-bottom:1px solid #e2e8f0;">
                                    <td style="padding:10px; font-weight:700; color:#0f172a;">{row.get("tld")}</td>
                                    <td style="padding:10px; color:#64748b;">{row.get("field")}</td>
                                    <td style="padding:10px; font-weight:600; color:#0f172a;">{comp_p:,.0f}đ</td>
                                    <td style="padding:10px; font-weight:600; color:#2563eb;">{lv_p:,.0f}đ</td>
                                    <td style="padding:10px;">{status_html}</td>
                                </tr>
            """

        html += """
                            </tbody>
                        </table>
        """

        # Price Changes section (if any)
        if price_changes:
            html += f"""
                        <h3 style="color:#0f172a; font-size:15px; margin:20px 0 10px 0;">📈 Biến Động Giá Phát Hiện ({len(price_changes)} mục)</h3>
                        <table width="100%" border="0" cellpadding="8" cellspacing="0" style="border-collapse:collapse; font-size:12px; margin-bottom:20px;">
                            <tr style="background-color:#f1f5f9;">
                                <th>TLD</th><th>Mục</th><th>Giá cũ</th><th>Giá mới</th>
                            </tr>
            """
            for pc in price_changes[:10]:
                html += f"""
                            <tr style="border-bottom:1px solid #e2e8f0;">
                                <td><strong>{pc.get("tld")}</strong></td>
                                <td>{pc.get("field")}</td>
                                <td>{pc.get("old_price",0):,.0f}đ</td>
                                <td style="color:#dc2626; font-weight:700;">{pc.get("new_price",0):,.0f}đ</td>
                            </tr>
                """
            html += "</table>"

        # AI Analysis box
        if ai_analysis:
            html += f"""
                        <div style="background-color:#eff6ff; border-left:4px solid #3b82f6; border-radius:4px; padding:16px 20px; margin:20px 0;">
                            <h3 style="color:#1e40af; font-size:14px; margin:0 0 8px 0;">🧠 Phân Tích & Hướng Đi Chiến Lược</h3>
                            <div style="font-size:13px; line-height:1.6; color:#1e3a8a; white-space:pre-wrap;">{ai_analysis}</div>
                        </div>
            """

        # DASHBOARD BUTTON & LINK
        dashboard_url = os.getenv("DASHBOARD_URL", "https://khangthost.io.vn")
        html += f"""
                        <div style="text-align:center; margin-top:28px; margin-bottom:12px;">
                            <a href="{dashboard_url}" style="background-color:#2563eb; color:#ffffff; text-decoration:none; padding:12px 28px; border-radius:6px; font-size:14px; font-weight:700; display:inline-block;">🌐 Mở Live Dashboard Xem Chi Tiết</a>
                            <p style="margin-top:10px; font-size:12px; color:#64748b;">
                                Link Dashboard: <a href="{dashboard_url}" style="color:#2563eb; font-weight:600;">{dashboard_url}</a>
                            </p>
                        </div>

                    </td>
                </tr>
                <tr>
                    <td style="background-color:#f8fafc; border-top:1px solid #e2e8f0; padding:16px 32px; text-align:center; font-size:12px; color:#94a3b8;">
                        Market AI Engine &bull; Hệ thống giám sát đối thủ 24/7 cho Long Vân Cloud Solution<br>
                        Email tự động — Vui lòng không trả lời trực tiếp email này.
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return html

