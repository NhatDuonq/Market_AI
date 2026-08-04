import os
import sys
import json
import glob
from datetime import datetime
import streamlit as st
import pandas as pd
import altair as alt

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.diff_engine import DiffEngine
from core.telegram_notifier import TelegramNotifier
from core.ai_analyzer import AIAnalyzer
from core.email_notifier import EmailNotifier

CONFIG_PATH = os.path.join(project_root, "config", "crawler_targets.json")


def load_targets_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Lỗi đọc file cấu hình: {e}")
    return {}


def save_targets_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Lỗi ghi cấu hình: {e}")
        return False


# Page Config
st.set_page_config(
    page_title="Market AI - Giám Sát Tên Miền Cạnh Tranh",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - Premium Dark Mode with Glassmorphism
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .main { background-color: #0f172a; color: #f8fafc; }

    /* KPI Cards */
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0; }
    .kpi-card {
        background: rgba(30, 41, 59, 0.85);
        backdrop-filter: blur(12px);
        padding: 20px;
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
        text-align: center;
        transition: transform 0.25s ease, box-shadow 0.25s ease;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(59, 130, 246, 0.15);
    }
    .kpi-value { font-size: 32px; font-weight: 800; line-height: 1.1; }
    .kpi-label { font-size: 12px; color: #94a3b8; margin-top: 6px; letter-spacing: 0.3px; }
    .kpi-value.blue { color: #60a5fa; }
    .kpi-value.red { color: #f87171; }
    .kpi-value.green { color: #34d399; }
    .kpi-value.amber { color: #fbbf24; }

    /* AI Insight Card */
    .ai-card {
        background: linear-gradient(145deg, rgba(30, 58, 95, 0.9), rgba(15, 23, 42, 0.95));
        border-left: 4px solid #3b82f6;
        padding: 24px;
        border-radius: 14px;
        margin: 16px 0;
        line-height: 1.7;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        white-space: pre-wrap;
    }

    /* TLD Badges */
    .badge-exclusive { display: inline-block; background: #10b981; color: white; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; margin: 2px; }
    .badge-missing { display: inline-block; background: #ef4444; color: white; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; margin: 2px; }
    .badge-common { display: inline-block; background: #475569; color: #e2e8f0; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; margin: 2px; }

    /* Section Separator */
    .section-sep { border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 28px 0; }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        font-weight: 600;
        border-radius: 10px;
        border: none;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    }

    /* Streamlit Metrics Styling */
    .stMetric {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(10px);
        padding: 18px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Login Container */
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 40px;
        background: rgba(30, 41, 59, 0.8);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,0.1);
        text-align: center;
        box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
</style>
""", unsafe_allow_html=True)

# Authentication
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


def check_password():
    pwd = os.getenv("DASHBOARD_PASSWORD", "123456")
    if st.session_state.get("login_pwd") == pwd:
        st.session_state["authenticated"] = True
    else:
        st.error("Mật khẩu không đúng!")


if not st.session_state["authenticated"]:
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown("### 🔐 Đăng nhập Market AI")
    st.text_input("Mật khẩu", type="password", key="login_pwd", on_change=check_password)
    st.button("Đăng nhập", on_click=check_password)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# Initialize engines
diff_engine = DiffEngine()
notifier = TelegramNotifier()
ai_analyzer = AIAnalyzer()
email_notifier = EmailNotifier()

# ============================================================
# SIDEBAR - Clean Navigation
# ============================================================
st.sidebar.title("⚡ Market AI")
st.sidebar.caption("Giám Sát Tên Miền & Tư Vấn Chiến Lược Long Vân")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Điều hướng",
    [
        "📊 Tổng Quan Cạnh Tranh",
        "🔍 Phân Tích Thị Phần TLD",
        "📈 Lịch Sử Biến Động Giá",
        "📸 Thư Viện Screenshots",
        "⚙️ Cấu Hình Hệ Thống"
    ]
)

st.sidebar.markdown("---")

# Competitor Provider Dropdown
COMPETITORS = {
    "matbao": "Mắt Bão",
    "pavietnam": "PA Việt Nam"
}

selected_competitor = st.sidebar.selectbox(
    "🏢 Chọn đối thủ so sánh:",
    list(COMPETITORS.keys()),
    format_func=lambda x: COMPETITORS[x]
)

competitor_display_name = COMPETITORS[selected_competitor]

# ============================================================
# TAB 1: TỔNG QUAN CẠNH TRANH (DASHBOARD)
# ============================================================
if menu == "📊 Tổng Quan Cạnh Tranh":
    st.title(f"📊 Tổng Quan Cạnh Tranh: Long Vân vs {competitor_display_name}")
    st.caption("So sánh trực quan vị thế giá tên miền. Long Vân = Benchmark chuẩn.")

    # Load data
    comp_snap = diff_engine.load_last_snapshot(f"{selected_competitor}_domain")
    comp_items = comp_snap.get("items", [])
    diff_data = diff_engine.compare_product_data_readonly(
        f"{selected_competitor}_domain", "domain", comp_items, url=comp_snap.get("url", "")
    ) if comp_items else {}

    lv_summary = diff_data.get("longvan_summary", {})
    cheaper_count = lv_summary.get("cheaper_count", 0)
    expensive_count = lv_summary.get("expensive_count", 0)
    tld_avail = diff_data.get("tld_availability", {})
    updated_at = comp_snap.get("updated_at", "Chưa có dữ liệu")

    # KPI Cards
    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-value blue">{len(comp_items)}</div>
            <div class="kpi-label">Tổng TLD {competitor_display_name}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value red">{cheaper_count}</div>
            <div class="kpi-label">Đối thủ RẺ hơn LV ⚠️</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value green">{expensive_count}</div>
            <div class="kpi-label">Long Vân RẺ hơn ✅</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value amber">{len(tld_avail.get('competitor_exclusive', []))}</div>
            <div class="kpi-label">TLD LV bỏ lỡ 🏷️</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption(f"🕐 Cập nhật gần nhất: {updated_at}")
    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)

    # AI Insight Card
    st.subheader(f"🧠 Tư Vấn AI Chiến Lược ({competitor_display_name})")
    if diff_data:
        ai_advice = ai_analyzer.analyze_market_changes(competitor_display_name, "domain", diff_data)
        st.markdown(f'<div class="ai-card">{ai_advice}</div>', unsafe_allow_html=True)
    else:
        st.info("Chưa có dữ liệu. Vui lòng chạy crawler trước.")

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)

    # Charts Grid
    st.subheader("📈 Trực Quan Hóa Giá")
    lv_comp = diff_data.get("longvan_comparison", [])
    if lv_comp:
        # Lọc chỉ lấy "Giá đăng ký" để biểu đồ gọn
        reg_only = [c for c in lv_comp if c.get("field") == "Giá đăng ký"]

        chart_col1, chart_col2 = st.columns([2, 1])

        with chart_col1:
            st.markdown(f"**So sánh Giá Đăng Ký: {competitor_display_name} vs Long Vân**")
            if reg_only:
                df_chart = pd.DataFrame(reg_only)
                df_chart["Sản Phẩm"] = df_chart["tld"]
                df_chart[f"Giá {competitor_display_name}"] = df_chart["competitor_price"].astype(float)
                df_chart["Giá Long Vân"] = df_chart["longvan_price"].astype(float)

                df_melt = pd.melt(
                    df_chart, id_vars=['Sản Phẩm'],
                    value_vars=[f"Giá {competitor_display_name}", "Giá Long Vân"],
                    var_name='Nhà Cung Cấp', value_name='Giá (VNĐ)'
                )

                bar_chart = alt.Chart(df_melt).mark_bar(opacity=0.85, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X('Sản Phẩm:N', sort=None, title="TLD"),
                    y=alt.Y('Giá (VNĐ):Q', title="Giá (VNĐ)"),
                    color=alt.Color('Nhà Cung Cấp:N', scale=alt.Scale(
                        domain=[f"Giá {competitor_display_name}", "Giá Long Vân"],
                        range=['#f87171', '#60a5fa']
                    )),
                    xOffset='Nhà Cung Cấp:N',
                    tooltip=['Sản Phẩm', 'Nhà Cung Cấp', alt.Tooltip('Giá (VNĐ):Q', format=',.0f')]
                ).properties(height=360).interactive()
                st.altair_chart(bar_chart, use_container_width=True)

        with chart_col2:
            st.markdown("**Tỷ Trọng Vị Thế Cạnh Tranh**")
            equal_count = len(reg_only) - cheaper_count - expensive_count
            if equal_count < 0:
                equal_count = 0
            donut_data = pd.DataFrame({
                'Vị thế': ['Đối thủ rẻ hơn', 'Long Vân rẻ hơn', 'Bằng giá'],
                'Số lượng': [cheaper_count, expensive_count, equal_count]
            })
            donut_data = donut_data[donut_data['Số lượng'] > 0]

            if not donut_data.empty:
                donut_chart = alt.Chart(donut_data).mark_arc(innerRadius=55, outerRadius=100).encode(
                    theta=alt.Theta(field="Số lượng", type="quantitative"),
                    color=alt.Color(field="Vị thế", type="nominal", scale=alt.Scale(
                        domain=['Đối thủ rẻ hơn', 'Long Vân rẻ hơn', 'Bằng giá'],
                        range=['#f87171', '#34d399', '#64748b']
                    )),
                    tooltip=['Vị thế', 'Số lượng']
                ).properties(height=300)
                st.altair_chart(donut_chart, use_container_width=True)

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)

    # Detailed Table
    st.subheader("🔍 Bảng Chi Tiết So Sánh Giá")
    filter_field = st.selectbox("Lọc theo tiêu chí:", ["Tất cả", "Giá đăng ký", "Giá gia hạn", "Giá chuyển đổi", "Tổng chi phí 2 năm"])
    search_q = st.text_input("🔍 Tìm kiếm TLD:", "")

    if lv_comp:
        df_table = pd.DataFrame(lv_comp)
        if filter_field != "Tất cả":
            df_table = df_table[df_table["field"] == filter_field]
        if search_q:
            df_table = df_table[df_table["tld"].str.contains(search_q, case=False, na=False)]

        if not df_table.empty:
            cols = ["tld", "field", "old_price", "competitor_price", "competitor_diff", "longvan_price", "diff_amount", "diff_pct", "status"]
            df_display = df_table[cols].copy()
            df_display.columns = [
                "TLD", "Hạng Mục", f"Giá Cũ {competitor_display_name}",
                f"Giá Mới {competitor_display_name}", f"Biến Động",
                "Giá Long Vân", "Chênh Lệch (VNĐ)", "Chênh Lệch (%)", "Vị Thế LV"
            ]
            df_display[f"Giá Cũ {competitor_display_name}"] = df_display[f"Giá Cũ {competitor_display_name}"].map("{:,.0f}đ".format)
            df_display[f"Giá Mới {competitor_display_name}"] = df_display[f"Giá Mới {competitor_display_name}"].map("{:,.0f}đ".format)
            df_display["Biến Động"] = df_display["Biến Động"].map("{:+,.0f}đ".format)
            df_display["Giá Long Vân"] = df_display["Giá Long Vân"].map("{:,.0f}đ".format)
            df_display["Chênh Lệch (VNĐ)"] = df_display["Chênh Lệch (VNĐ)"].map("{:+,.0f}đ".format)
            df_display["Chênh Lệch (%)"] = df_display["Chênh Lệch (%)"].map("{:+.1f}%".format)
            df_display["Vị Thế LV"] = df_display["Vị Thế LV"].map({
                "CHEAPER": "⚠️ Đối thủ rẻ hơn",
                "EXPENSIVE": "✅ LV rẻ hơn",
                "EQUAL": "⚖️ Bằng giá"
            })
            st.dataframe(df_display, use_container_width=True, height=420)
        else:
            st.info("Không tìm thấy kết quả phù hợp.")
    else:
        st.info("Chưa có dữ liệu so sánh. Vui lòng chạy crawler.")

# ============================================================
# TAB 2: PHÂN TÍCH THỊ PHẦN TLD
# ============================================================
elif menu == "🔍 Phân Tích Thị Phần TLD":
    st.title(f"🔍 Phân Tích Độ Phủ TLD: Long Vân vs {competitor_display_name}")
    st.caption("Phát hiện lỗ hổng thị phần và lợi thế ngách của Long Vân")

    tld_avail = diff_engine.analyze_tld_availability(f"{selected_competitor}_domain")

    lv_exclusive = tld_avail.get("longvan_exclusive", [])
    comp_exclusive = tld_avail.get("competitor_exclusive", [])
    common = tld_avail.get("common", [])
    lv_total = tld_avail.get("longvan_total", 0)
    comp_total = tld_avail.get("competitor_total", 0)

    # KPI
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Long Vân TLD", f"{lv_total} đuôi")
    with c2:
        st.metric(f"{competitor_display_name} TLD", f"{comp_total} đuôi")
    with c3:
        st.metric("TLD Chung (Giao)", f"{len(common)} đuôi")
    with c4:
        overlap_pct = (len(common) / max(lv_total, 1)) * 100
        st.metric("Độ phủ chung", f"{overlap_pct:.0f}%")

    st.markdown("---")

    col_lv, col_comp = st.columns(2)
    with col_lv:
        st.subheader(f"✅ Lợi Thế Ngách Long Vân ({len(lv_exclusive)} TLD)")
        st.caption(f"Các TLD chỉ Long Vân bán, {competitor_display_name} KHÔNG có")
        if lv_exclusive:
            badges = " ".join([f'<span class="badge-exclusive">{tld}</span>' for tld in lv_exclusive])
            st.markdown(badges, unsafe_allow_html=True)
        else:
            st.success("Tất cả TLD Long Vân đều có ở đối thủ.")

    with col_comp:
        st.subheader(f"⚠️ Thị Phần Bỏ Lỡ ({len(comp_exclusive)} TLD)")
        st.caption(f"Các TLD {competitor_display_name} bán mà Long Vân KHÔNG có")
        if comp_exclusive:
            badges = " ".join([f'<span class="badge-missing">{tld}</span>' for tld in comp_exclusive])
            st.markdown(badges, unsafe_allow_html=True)
        else:
            st.info("Long Vân đã phủ hết các TLD mà đối thủ có.")

    st.markdown("---")
    st.subheader(f"🤝 TLD Cùng Bán ({len(common)} đuôi)")
    if common:
        badges = " ".join([f'<span class="badge-common">{tld}</span>' for tld in common])
        st.markdown(badges, unsafe_allow_html=True)

    # Screenshot kiểm chứng
    st.markdown("---")
    st.subheader("📸 Ảnh Chụp Đối Soát")
    screenshots = glob.glob(os.path.join(project_root, "storage", "screenshots", f"{selected_competitor}_*.png"))
    screenshots.sort(key=os.path.getctime, reverse=True)
    if screenshots:
        st.image(screenshots[0], caption=f"Screenshot mới nhất - {competitor_display_name}", use_container_width=True)
    else:
        st.info("Chưa có ảnh chụp cho đối thủ này.")

# ============================================================
# TAB 3: LỊCH SỬ BIẾN ĐỘNG GIÁ
# ============================================================
elif menu == "📈 Lịch Sử Biến Động Giá":
    st.title(f"📈 Lịch Sử Biến Động Giá: {competitor_display_name}")
    st.caption("Theo dõi các đợt thay đổi giá của đối thủ qua thời gian")

    history = diff_engine.get_price_history(f"{selected_competitor}_domain", limit=10)

    if history:
        st.markdown(f"**{len(history)} bản ghi lịch sử gần nhất:**")
        for idx, snap in enumerate(history):
            with st.expander(f"📅 {snap['updated_at']} — {snap['total_items']} TLD", expanded=(idx == 0)):
                df_hist = pd.DataFrame(snap["items"])
                if not df_hist.empty:
                    cols_to_show = ["tld", "register_price", "renew_price", "transfer_price"]
                    available_cols = [c for c in cols_to_show if c in df_hist.columns]
                    df_show = df_hist[available_cols].copy()
                    rename_map = {
                        "tld": "TLD",
                        "register_price": "Giá Đăng Ký",
                        "renew_price": "Giá Gia Hạn",
                        "transfer_price": "Giá Chuyển Đổi"
                    }
                    df_show = df_show.rename(columns={k: v for k, v in rename_map.items() if k in df_show.columns})
                    for col in ["Giá Đăng Ký", "Giá Gia Hạn", "Giá Chuyển Đổi"]:
                        if col in df_show.columns:
                            df_show[col] = df_show[col].map("{:,.0f}đ".format)
                    st.dataframe(df_show, use_container_width=True)
    else:
        st.info("Chưa có lịch sử biến động. Chạy crawler nhiều lần để tích lũy dữ liệu.")

    # Long Van benchmark history
    st.markdown("---")
    st.subheader("🏠 Lịch Sử Snapshot Long Vân (Benchmark)")
    lv_history = diff_engine.get_price_history("longvan_domain", limit=5)
    if lv_history:
        for snap in lv_history[:3]:
            with st.expander(f"📅 {snap['updated_at']} — {snap['total_items']} TLD"):
                df_lv = pd.DataFrame(snap["items"])
                if not df_lv.empty:
                    st.dataframe(df_lv, use_container_width=True)
    else:
        lv_snap = diff_engine.load_longvan_snapshot("domain")
        if lv_snap.get("items"):
            st.markdown(f"**Snapshot hiện tại:** {lv_snap.get('updated_at', 'N/A')}")
            st.dataframe(pd.DataFrame(lv_snap["items"]), use_container_width=True)
        else:
            st.info("Chưa có snapshot Long Vân.")

# ============================================================
# TAB 4: THƯ VIỆN SCREENSHOTS
# ============================================================
elif menu == "📸 Thư Viện Screenshots":
    st.title("📸 Thư Viện Ảnh Chụp Giao Diện Đối Thủ")
    st.caption("Ảnh được chụp tự động mỗi lần crawler chạy bằng Playwright")

    screenshots = glob.glob(os.path.join(project_root, "storage", "screenshots", "*.png"))
    screenshots.sort(key=os.path.getctime, reverse=True)

    if screenshots:
        # Bộ lọc theo nhà cung cấp
        filter_provider = st.selectbox("Lọc theo nguồn:", ["Tất cả", "Long Vân", "Mắt Bão", "PA Việt Nam"])
        filter_map = {"Long Vân": "longvan", "Mắt Bão": "matbao", "PA Việt Nam": "pavietnam"}

        if filter_provider != "Tất cả":
            prefix = filter_map.get(filter_provider, "")
            screenshots = [s for s in screenshots if os.path.basename(s).startswith(prefix)]

        if screenshots:
            cols_per_row = 2
            for i in range(0, len(screenshots), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(screenshots):
                        with col:
                            st.image(screenshots[idx], caption=os.path.basename(screenshots[idx]), use_container_width=True)
        else:
            st.info("Không tìm thấy ảnh phù hợp với bộ lọc.")
    else:
        st.info("Chưa có ảnh chụp màn hình nào. Chạy crawler để tạo ảnh.")

# ============================================================
# TAB 5: CẤU HÌNH HỆ THỐNG
# ============================================================
elif menu == "⚙️ Cấu Hình Hệ Thống":
    st.title("⚙️ Cấu Hình Hệ Thống & Công Tắc Crawler")

    # Crawler Toggles
    st.subheader("🕷️ Công Tắc Cào Dữ Liệu")
    targets = load_targets_config()
    updated = False

    for p_key, p_info in targets.items():
        st.markdown(f"**🏢 {p_info.get('name', p_key)}**")
        prods = p_info.get("products", {})
        for prod_key, prod_info in prods.items():
            label = f"{prod_info.get('name')} (`{prod_key}`)"
            is_on = st.toggle(label, value=prod_info.get("enabled", False), key=f"tgl_{p_key}_{prod_key}")
            if is_on != prod_info.get("enabled", False):
                prod_info["enabled"] = is_on
                updated = True
        st.markdown("---")

    if updated:
        if save_targets_config(targets):
            st.toast("💾 Đã lưu cấu hình!", icon="✅")

    # System credentials
    st.subheader("🔐 Thông Tin Kết Nối")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Telegram Bot**")
        st.code(f"Token: {'Đã cấu hình ✅' if os.getenv('TELEGRAM_BOT_TOKEN') else 'Chưa đặt ❌'}")
        st.code(f"Chat ID: {os.getenv('TELEGRAM_CHAT_ID', 'Chưa đặt')}")
    with col_b:
        st.markdown("**Email (SMTP)**")
        st.code(f"SMTP: {'Đã cấu hình ✅' if email_notifier.is_configured() else 'Chưa đặt ❌'}")
        st.code(f"To: {os.getenv('EMAIL_TO', 'Chưa đặt')}")

    st.markdown("---")
    st.markdown("**AI & Crawler**")
    st.code(f"Gemini AI: {'Đã cấu hình ✅' if ai_analyzer.is_configured() else 'Chưa đặt (Rule-based AI) ❌'}")
    st.code(f"Tần suất quét: Mỗi {os.getenv('CRAWL_INTERVAL_MINUTES', '30')} phút/lần")
