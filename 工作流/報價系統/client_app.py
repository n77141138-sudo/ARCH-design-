import base64
import datetime
import io
import json
import os
import random
import string
from pathlib import Path

import streamlit as st
from PIL import Image

import cloud_manager

# === 頁面設定 ===
st.set_page_config(page_title="工程報價查詢系統｜JYY DESIGN", page_icon="◈", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #fcfbf9; color: #333333; }
    h1, h2, h3 { color: #bfa15f !important; font-family: 'Helvetica Neue', sans-serif; font-weight: 300; }
    .stButton > button {
        background-color: #ffffff; color: #bfa15f; border: 1px solid #bfa15f;
        border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: all 0.3s ease;
    }
    .stButton > button:hover { background-color: #bfa15f; color: #ffffff; box-shadow: 0 6px 12px rgba(191,161,95,0.2); }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; border-radius: 4px; color: #666666; font-weight: 500; }
    .stTabs [aria-selected="true"] { color: #bfa15f !important; border-bottom: 2px solid #bfa15f !important; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "quotes_db.json"
FLOORPLAN_DIR = BASE_DIR / "uploads" / "floorplans"
FLOORPLAN_DIR.mkdir(parents=True, exist_ok=True)


def load_db() -> dict:
    db = cloud_manager.load_db_from_cloud()
    if not db:
        if DB_PATH.exists():
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    return db


def save_db(db: dict) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    cloud_manager.save_db_to_cloud(db)


def generate_random_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def compress_image_to_b64(file_bytes: bytes, max_width: int = 800, quality: int = 40) -> str:
    """
    壓縮圖片至指定寬度並轉為 base64 字串。
    目標壓縮後 < 35KB，使 base64 能存入 Google Sheets 單格（50,000 char 限制）。
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"圖片壓縮失敗：{e}")


# === UI ===
st.markdown("<h1 style='text-align: center; color: #c9a84c;'>◈ JYY DESIGN 客戶入口平台</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>請選擇您的工程項目，或輸入專屬單號查詢進度。</p>", unsafe_allow_html=True)
st.write("---")

tab1, tab2, tab3, tab4 = st.tabs(["🏗️ 預售客變", "📐 室內設計", "🧱 基礎工程", "🔨 裝修工程"])


def render_query_section(category: str):
    query_code = st.text_input(f"輸入專屬單號 ({category})", placeholder="例如：A1B2C3", key=f"query_{category}")
    if st.button("查詢報價", key=f"btn_{category}", type="primary", use_container_width=True):
        if not query_code:
            st.warning("請輸入報價單號！")
        else:
            db = load_db()
            code = query_code.strip().upper()
            if code in db and db[code].get("category") == category:
                record = db[code]
                info = db[code]
                st.success(f"✅ 找到 {info['project_name']} 的報價單！")

                if info.get("category") == "室內設計":
                    st.write("---")
                    st.subheader("🎨 設計案進度與圖面")
                    phase = info.get("design_phase", "接洽中")
                    st.info(f"📍 目前設計階段：**{phase}**")

                if record.get("status") == "已提交，等待 AI 分析中":
                    st.info(f"您的案件狀態：{record.get('status')}")
                else:
                    st.success(f"您的案件狀態：{record.get('status')}")
                    if "markdown_quote" in record:
                        st.markdown(record["markdown_quote"])
                    excel_url = record.get("excel_drive_url")
                    if excel_url:
                        st.link_button("📥 下載 Excel 報價單 (Google Drive)", excel_url)
            else:
                st.error("❌ 找不到此單號，或該單號不屬於此分類。")


with tab1:
    st.subheader("📝 預售客變申請與查詢")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.info("💡 **新客戶申請**\n\n上傳您的建商平面圖，我們將利用 AI 快速為您分析並提供估價。")
        client_name = st.text_input("您的姓名 / 稱呼")
        client_phone = st.text_input("聯絡電話")
        uploaded_fp = st.file_uploader("上傳圖面 (支援 JPG, PNG, PDF)", type=["jpg", "jpeg", "png", "pdf"])

        if st.button("上傳圖面並取得單號"):
            if not client_name or not client_phone or not uploaded_fp:
                st.error("請填寫姓名、電話並上傳圖面。")
            else:
                new_code = generate_random_code()
                file_bytes = uploaded_fp.getvalue()
                floorplan_b64 = ""

                with st.spinner("正在壓縮並同步圖面至雲端..."):
                    # PDF 不壓縮，直接略過 b64 (太大)
                    if uploaded_fp.type != "application/pdf":
                        try:
                            floorplan_b64 = compress_image_to_b64(file_bytes)
                            kb = len(base64.b64decode(floorplan_b64)) // 1024
                            st.caption(f"✅ 圖面壓縮完成：約 {kb} KB")
                        except Exception as e:
                            st.warning(f"⚠️ 圖面壓縮失敗，將不含預覽圖：{e}")
                    else:
                        st.info("PDF 圖面已記錄，後台請另行確認。")

                    db = load_db()
                    db[new_code] = {
                        "category": "預售客變",
                        "date": datetime.datetime.now().strftime("%Y/%m/%d"),
                        "project_name": "客變申請案件",
                        "client_name": client_name,
                        "client_phone": client_phone,
                        "floorplan_b64": floorplan_b64,
                        "floorplan_path": "",
                        "floorplan_drive_url": "",
                        "status": "已提交，等待 AI 分析中"
                    }
                    save_db(db)

                st.success(f"🎉 上傳成功！\n\n您的專屬查詢單號為：**{new_code}**\n\n請務必記下此單號，日後可於右側查詢估價結果。")

    with col2:
        st.write("🔍 **已有單號？查詢估價結果**")
        render_query_section("預售客變")

# === 室內設計 ===
with tab2:
    render_query_section("室內設計")

# === 基礎工程 ===
with tab3:
    render_query_section("基礎工程")

# === 裝修工程 ===
with tab4:
    render_query_section("裝修工程")
