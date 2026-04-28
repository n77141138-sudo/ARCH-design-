import streamlit as st
import json
import os
import random
import string
import datetime
from pathlib import Path
import cloud_manager

# === 頁面設定 ===
st.set_page_config(page_title="工程報價查詢系統｜JYY DESIGN", page_icon="◈", layout="centered")

st.markdown("""
<style>
    /* Premium Light Mode Styling */
    .stApp {
        background-color: #fcfbf9;
        color: #333333;
    }
    h1, h2, h3 {
        color: #bfa15f !important; /* Elegant Gold */
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 300;
    }
    .stButton > button {
        background-color: #ffffff;
        color: #bfa15f;
        border: 1px solid #bfa15f;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #bfa15f;
        color: #ffffff;
        box-shadow: 0 6px 12px rgba(191,161,95,0.2);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px;
        color: #666666;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        color: #bfa15f !important;
        border-bottom: 2px solid #bfa15f !important;
    }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "quotes_db.json"
FLOORPLAN_DIR = BASE_DIR / "uploads" / "floorplans"

FLOORPLAN_DIR.mkdir(parents=True, exist_ok=True)

def load_db():
    # 優先從雲端載入
    db = cloud_manager.load_db_from_cloud()
    if not db:
        # 雲端失敗或為空，嘗試從本機載入
        if DB_PATH.exists():
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    return db

def save_db(db):
    # 同時寫入本機與雲端
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    cloud_manager.save_db_to_cloud(db)

def generate_random_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# === UI 開始 ===
st.markdown("<h1 style='text-align: center; color: #c9a84c;'>◈ JYY DESIGN 客戶入口平台</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>請選擇您的工程項目，或輸入專屬單號查詢進度。</p>", unsafe_allow_html=True)

st.write("---")

tab1, tab2, tab3, tab4 = st.tabs(["🏗️ 預售客變", "📐 室內設計", "🧱 基礎工程", "🔨 裝修工程"])

# 渲染報價查詢區塊的共用函式
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
                md_path = BASE_DIR / record.get("md_path", "")
                xlsx_path = BASE_DIR / record.get("xlsx_path", "")
                info = db[code]
                st.success(f"✅ 找到 {info['project_name']} 的報價單！")
                
                # --- 室內設計專屬展示 ---
                if info.get("category") == "室內設計":
                    st.write("---")
                    st.subheader("🎨 設計案進度與圖面")
                    
                    # 顯示進度
                    phase = info.get("design_phase", "接洽中")
                    st.info(f"📍 目前設計階段：**{phase}**")
                    
                st.success(f"✅ 找到 {record['project_name']} 的報價單！")
                
                if record.get("status") == "已提交，等待 AI 分析中":
                    st.info(f"您的案件狀態：{record.get('status')}")
                    if record.get("floorplan_drive_url"):
                        st.link_button("查看已上傳圖面 (Google Drive)", record.get("floorplan_drive_url"))
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
        uploaded_fp = st.file_uploader("上傳圖面 (支援 PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"])
        
        if st.button("上傳圖面並取得單號"):
            if not client_name or not client_phone or not uploaded_fp:
                st.error("請填寫姓名、電話並上傳圖面。")
            else:
                new_code = generate_random_code()
                file_bytes = uploaded_fp.getvalue()
                safe_filename = f"{new_code}_{uploaded_fp.name}"

                # 優先直接從記憶體上傳至 Google Drive（Streamlit Cloud 環境）
                st.info("正在同步圖面至雲端...")
                drive_url = cloud_manager.upload_bytes_to_drive(file_bytes, safe_filename)

                # 若 Drive 上傳失敗，嘗試寫本機備份
                local_path_str = ""
                if not drive_url:
                    try:
                        save_path = FLOORPLAN_DIR / safe_filename
                        with open(save_path, "wb") as f:
                            f.write(file_bytes)
                        local_path_str = str(save_path)
                        st.warning("⚠️ 雲端上傳失敗，已備份至本機。請確認 Google 憑證設定。")
                    except Exception as save_err:
                        st.warning(f"⚠️ 雲端與本機儲存皆失敗：{save_err}")

                db = load_db()
                db[new_code] = {
                    "category": "預售客變",
                    "date": datetime.datetime.now().strftime("%Y/%m/%d"),
                    "project_name": "客變申請案件",
                    "client_name": client_name,
                    "client_phone": client_phone,
                    "floorplan_path": local_path_str,
                    "floorplan_drive_url": drive_url or "",
                    "status": "已提交，等待 AI 分析中"
                }
                save_db(db)

                if drive_url:
                    st.success(f"🎉 上傳成功！\n\n您的專屬查詢單號為：**{new_code}**\n\n請務必記下此單號，日後可於右側查詢估價結果。")
                else:
                    st.warning(f"⚠️ 上傳已記錄，但雲端同步失敗。單號：**{new_code}**。請聯絡設計師確認。")
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
