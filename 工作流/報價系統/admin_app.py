import streamlit as st
import json
import os
import random
import string
import datetime
from pathlib import Path
import sys

# 載入核心邏輯
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
import sys
import cloud_manager
import agent_ana
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

try:
    import ocr_parser
except ImportError:
    ocr_parser = None

# === 頁面與路徑設定 ===
st.set_page_config(page_title="後台管理｜JYY DESIGN", page_icon="⚙️", layout="wide")

st.markdown("""
<style>
    /* Premium Dark Mode Styling */
    .stApp {
        background-color: #0b0f19;
        color: #e0e0e0;
    }
    h1, h2, h3, h4 {
        color: #d4af37 !important; /* Gold */
    }
    .stButton > button {
        background-color: #1a2a42;
        color: #ffffff;
        border: 1px solid #d4af37;
        border-radius: 6px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #d4af37;
        color: #0b0f19;
        border-color: #ffffff;
    }
    .css-1d391kg {  /* Sidebar */
        background-color: #121a2f;
    }
    div[data-testid="stMetricValue"] {
        color: #d4af37;
    }
</style>
""", unsafe_allow_html=True)

INPUT_DIR  = BASE_DIR / "01_vendor_quotes_input"
OUTPUT_DIR = BASE_DIR / "02_client_quotes_output"
REVIEW_DIR = BASE_DIR / "03_review_summaries"
DB_PATH = BASE_DIR / "quotes_db.json"
CONFIG_PATH = BASE_DIR / "config.json"
FLOORPLAN_DIR = BASE_DIR / "uploads" / "floorplans"

for d in [INPUT_DIR, OUTPUT_DIR, REVIEW_DIR, FLOORPLAN_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def load_db():
    # 優先從雲端載入
    db = cloud_manager.load_db_from_cloud()
    if not db:
        if DB_PATH.exists():
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    return db

def save_db(data):
    # 同時儲存本機與雲端
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    cloud_manager.save_db_to_cloud(data)

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def generate_random_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# === 登入機制 ===
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    st.title("🔒 後台管理登入")
    pwd = st.text_input("請輸入管理員密碼", type="password")
    if st.button("登入"):
        if pwd == "NCKU123":
            st.session_state.admin_logged_in = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()

# === 系統變數初始化 ===
if "api_tokens_used" not in st.session_state:
    st.session_state.api_tokens_used = 0

cfg = load_config()
api_key = os.getenv("GEMINI_API_KEY", "")
db = load_db()

# --- 側邊欄：全局設定與分類切換 ---
with st.sidebar:
    st.header("⚙️ 系統切換")
    # 分類選擇
    CATEGORIES = ["預售客變", "室內設計", "基礎工程", "裝修工程"]
    selected_category = st.selectbox("請選擇工程分類", CATEGORIES)
    
    st.markdown("---")
    st.header("🔑 API 設定")
    if not api_key:
        st.warning("⚠️ 系統尚未偵測到 API Key。請確保根目錄的 `.env` 檔案內包含 `GEMINI_API_KEY=您的金鑰`。")
    else:
        st.success("✅ 已載入環境變數中的 API Key")
        
    st.markdown("---")
    st.metric("🤖 API Token 耗損", f"{st.session_state.api_tokens_used:,}")
    cost_usd = (st.session_state.api_tokens_used / 1000000) * 0.075 # Gemini Flash 大約估算
    st.caption(f"預估花費：約 NT$ {cost_usd * 32:.4f}")

# === 主畫面 ===
st.title(f"📁 【{selected_category}】管理面板")

# 篩選該分類的案件
category_items = [(code, info) for code, info in db.items() if info.get("category") == selected_category]

# 建立下拉選單的選項列表 (格式: 單號 - 案件名稱)
dropdown_options = ["(新增案件)"]
for code, info in category_items:
    p_name = info.get("project_name", "未命名")
    dropdown_options.append(f"{code} - {p_name}")

col_sel1, col_sel2 = st.columns([1, 2])
with col_sel1:
    selected_option = st.selectbox("選擇要處理的案件", dropdown_options)

if selected_option == "(新增案件)":
    selected_code = "(新增案件)"
    st.info("請在下方設定中產出新報價單，系統會自動分配新單號。")
    current_info = {}
else:
    selected_code = selected_option.split(" - ")[0]
    current_info = db.get(selected_code, {})

st.write("---")

# 針對不同的分類，顯示不同的工作區
if selected_category == "預售客變":
    st.subheader("📐 客變圖面 AI 估算區")
    
    if current_info and (
        current_info.get("floorplan_b64") or
        current_info.get("floorplan_drive_url") or
        current_info.get("floorplan_path")
    ):
        raw_fp = current_info.get("floorplan_path", "")
        fp_path = Path(raw_fp) if raw_fp else None
        drive_url = current_info.get("floorplan_drive_url", "")
        floorplan_b64 = current_info.get("floorplan_b64", "")
        phone_display = current_info.get("client_phone") or current_info.get("phone", "未提供")

        col_img, col_ai = st.columns(2)
        with col_img:
            st.write(f"**客戶：{current_info.get('client_name')} (Tel: {phone_display})**")

            # Priority 1: base64 圖片（最新機制，無需 Drive）
            if floorplan_b64:
                try:
                    import base64 as _b64
                    img_bytes = _b64.b64decode(floorplan_b64)
                    st.image(img_bytes, caption="客戶上傳的圖面", use_container_width=True)
                except Exception as decode_err:
                    st.warning(f"⚠️ 圖面解碼失敗：{decode_err}")
            # Priority 2: Google Drive URL
            elif drive_url:
                st.link_button("📎 查看已上傳圖面 (Google Drive)", drive_url)
                st.caption("圖面已同步至雲端，請點擊上方連結查看。")
            # Priority 3: 本機絕對路徑
            elif fp_path and fp_path.exists():
                if fp_path.suffix.lower() in ['.jpg', '.png', '.jpeg']:
                    st.image(str(fp_path), caption="客戶上傳的圖面", use_container_width=True)
                else:
                    st.info(f"已上傳 PDF 圖面：{fp_path.name}")
            else:
                st.warning("⚠️ 圖面資料不存在，可能尚未上傳成功。")
                
        with col_ai:
            if st.button("🤖 啟動 AI 比例尺分析", type="primary"):
                if not api_key:
                    st.error("請先設定 API Key！")
                elif not ocr_parser:
                    st.error("OCR 模組載入失敗")
                elif not floorplan_b64 and (fp_path is None or not fp_path.exists()):
                    st.error("⚠️ 本機找不到圖面檔案，無法執行 AI 分析。")
                else:
                    with st.spinner("AI 正在分析大門比例與計算總坪數..."):
                        try:
                            result = ocr_parser.analyze_floorplan(fp_path, api_key)
                            st.session_state.api_tokens_used += result.get("tokens", 0)
                            
                            st.success("✅ 分析完成！")
                            st.write(f"### 預估坪數：**{result.get('estimated_pings', 0)} 坪**")
                            st.info(f"**AI 判斷邏輯**：\n{result.get('reasoning', '')}")
                            
                            # 寫入狀態
                            db[selected_code]["estimated_pings"] = result.get('estimated_pings', 0)
                            save_db(db)
                        except Exception as e:
                            st.error(f"分析失敗：{e}")
            
            # 手陪設定與產出客變報價
            pings = current_info.get("estimated_pings", 0)
            ping_price = st.number_input("設定每坪單價 (客變設計費/工程費)", value=3000, step=500)
            
            if st.button("⚡ 產生客變專屬報價單"):
                if pings == 0:
                    st.warning("請先執行 AI 分析或手動確認坪數。")
                else:
                    # 建立一個虛擬的 vendor data 來餵給 agent_ana
                    virtual_vendor = [{
                        "vendor": "JYY DESIGN 內部估算",
                        "category": "預售客變工程",
                        "items": [{
                            "name": "客變工程依坪數計費",
                            "spec": "依 AI 比例尺推算",
                            "qty": pings,
                            "unit": "坪",
                            "unit_price": ping_price, # 這裡當成最終售價
                            "markup": 1.0 # 客變不加利潤率，直接算
                        }]
                    }]
                    
                    review_filename = f"審核_{selected_code}.xlsx"
                    quote_filename  = f"報價單_{selected_code}.xlsx"
                    md_filename     = f"報價單_{selected_code}.md"
                    
                    agent_ana.export_client_quote_excel(
                        virtual_vendor, 1.0, current_info.get("project_name", "客變專案"),
                        "客戶地址未提供", datetime.datetime.now().strftime("%Y/%m/%d"), 30, OUTPUT_DIR / quote_filename
                    )
                    agent_ana.export_markdown_quote(
                        virtual_vendor, 1.0, current_info.get("project_name", "客變專案"),
                        "客戶地址未提供", datetime.datetime.now().strftime("%Y/%m/%d"), 30, OUTPUT_DIR / md_filename
                    )
                    
                    db[selected_code]["md_path"] = f"02_client_quotes_output/{md_filename}"
                    db[selected_code]["xlsx_path"] = f"02_client_quotes_output/{quote_filename}"
                    db[selected_code]["status"] = "已完成"
                    save_db(db)
                    st.success("🎉 客變報價單已產生，客戶可於前台查詢。")
                    st.rerun()

    else:
        st.info("此分類通常由客戶於前台上傳圖面後生成單號。您也可以在下方切換到其他分類上傳廠商報價。")

# --- 室內設計專屬功能 (進度與照片) ---
elif selected_category == "室內設計":
    st.markdown("### 🎨 室內設計專案管理")
    
    # 設計階段選擇
    PHASES = ["平面配置討論中", "3D 渲染製作中", "施工圖繪製中", "材質挑選中", "設計定案", "結案"]
    current_phase = current_info.get("design_phase", PHASES[0])
    new_phase = st.selectbox("目前設計階段", PHASES, index=PHASES.index(current_phase) if current_phase in PHASES else 0)
    
    # 空間照片管理
    st.markdown("#### 📸 空間設計圖/渲染圖上傳")
    uploaded_design_files = st.file_uploader("選擇多張圖片上傳", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    existing_photos = current_info.get("design_photos", [])
    
    if uploaded_design_files:
        for idx, file in enumerate(uploaded_design_files):
            col_p1, col_p2 = st.columns([1, 3])
            with col_p1:
                st.image(file, width=150)
            with col_p2:
                location_name = st.text_input(f"空間名稱 (例如: 客廳, 主臥)", key=f"loc_{idx}")
                if st.button(f"確定上傳此圖", key=f"up_{idx}"):
                    # 儲存與上傳
                    temp_path = BASE_DIR / "uploads" / "design" / file.name
                    temp_path.parent.mkdir(exist_ok=True)
                    with open(temp_path, "wb") as f:
                        f.write(file.getbuffer())
                    
                    st.info("同步至雲端中...")
                    d_url = cloud_manager.upload_file_to_drive(temp_path)
                    existing_photos.append({"location": location_name, "url": d_url})
                    
                    # 更新資料庫
                    current_info["design_phase"] = new_phase
                    current_info["design_photos"] = existing_photos
                    db[selected_code] = current_info
                    save_db(db)
                    st.success(f"{location_name} 上傳成功！")
    
    if st.button("儲存目前進度狀態"):
        current_info["design_phase"] = new_phase
        db[selected_code] = current_info
        save_db(db)
        st.success("進度狀態已更新！")
    
    # 顯示已上傳的照片清單
    if existing_photos:
        st.markdown("---")
        st.write("已上傳照片：")
        for p in existing_photos:
            st.write(f"- {p['location']}: [點此查看]({p['url']})")

# === 一般工程產出流程 (室內設計/基礎/裝修) ===
st.markdown("---")
st.subheader("📝 傳統廠商報價整合區 (適用於各類工程)")

col_up, col_form = st.columns(2)

with col_up:
    st.write("**1. 上傳廠商報價單**")
    uploaded_files = st.file_uploader(
        "支援：PDF, JPG, Excel, JSON", 
        accept_multiple_files=True,
        type=['pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'xls', 'json'],
        key="vendor_upload"
    )
    
    if st.button("處理上傳檔案"):
        if not uploaded_files:
            st.warning("請先選擇檔案")
        else:
            with st.spinner("處理中... (若為圖片/PDF 將呼叫 AI 解析)"):
                for uf in uploaded_files:
                    save_path = INPUT_DIR / uf.name
                    with open(save_path, "wb") as f:
                        f.write(uf.getbuffer())
                    
                    suffix = save_path.suffix.lower()
                    if suffix in [".pdf", ".jpg", ".jpeg", ".png"]:
                        if not api_key:
                            st.error("需要設定 Gemini API Key！")
                            save_path.unlink()
                            continue
                        try:
                            result = ocr_parser.parse_quote_file(save_path, api_key)
                            parsed_data = result["data"]
                            st.session_state.api_tokens_used += result["tokens"]
                            
                            json_path = save_path.with_suffix(".json")
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(parsed_data, f, ensure_ascii=False, indent=2)
                            save_path.unlink() 
                            st.success(f"✅ AI 解析成功：{json_path.name}")
                        except Exception as e:
                            st.error(f"❌ 解析 {uf.name} 失敗：{e}")
                            save_path.unlink()
                    else:
                        st.success(f"✅ 已儲存：{uf.name}")
            st.rerun()

    st.write("---")
    st.write("**目前暫存的廠商檔案：**")
    files = list(INPUT_DIR.rglob("*.*"))
    for f in files:
        cc1, cc2 = st.columns([4, 1])
        cc1.write(f.name)
        if cc2.button("刪除", key=f"del_{f.name}"):
            f.unlink()
            st.rerun()
    if not files:
        st.info("尚無檔案。請上傳並處理。")

with col_form:
    st.write("**2. 產出對客報價單設定**")
    
    # 欄位優化：案件名稱、案件地址
    new_code = selected_code if selected_code != "(新增案件)" else generate_random_code()
    p_code = st.text_input("報價單號", value=new_code, disabled=(selected_code != "(新增案件)"))
    p_name = st.text_input("案件名稱", value=current_info.get("project_name", "盧公館 J042 室內裝修工程"))
    p_addr = st.text_input("案件地址", value=current_info.get("project_address", "台北市信義區..."))
    
    col_d1, col_d2 = st.columns(2)
    q_date = col_d1.date_input("報價日期", value=datetime.date.today())
    q_valid = col_d2.number_input("有效期限 (天)", value=30, min_value=1)
    
    # --- 利潤設定區 ---
    st.markdown("---")
    profit_mode = st.radio("📈 利潤計算模式", ["比例 (%)", "固定金額 (萬元)"], horizontal=True)
    
    # 計算總成本 (以便換算固定金額)
    agent_ana.INPUT_DIR = INPUT_DIR
    vendors = agent_ana.scan_input_folder()
    total_cost = 0
    if vendors:
        for v in vendors:
            for it in v["items"]:
                total_cost += it["unit_price"] * it["qty"]
    
    if profit_mode == "比例 (%)":
        markup_pct = st.slider("預設利潤率 (%)", 5, 50, 20)
        markup_rate = 1 + (markup_pct / 100)
        st.write(f"💡 目前設定：加價 {markup_pct}%")
    else:
        profit_wan = st.number_input("預計毛利金額 (萬元)", min_value=0.1, value=10.0, step=0.5)
        profit_amt = profit_wan * 10000
        if total_cost > 0:
            markup_rate = (total_cost + profit_amt) / total_cost
            actual_pct = (markup_rate - 1) * 100
            st.write(f"💡 自動換算：約加價 {actual_pct:.1f}% (總成本: {total_cost:,.0f})")
        else:
            markup_rate = 1.2
            st.warning("尚無成本資料，暫以 20% 計算")
    
    if st.button("⚡ 產出整合報價單", type="primary", use_container_width=True):
        agent_ana.OUTPUT_DIR = OUTPUT_DIR
        agent_ana.REVIEW_DIR = REVIEW_DIR
        
        vendors = agent_ana.scan_input_folder()
        if not vendors:
            st.error("沒有可用的廠商報價資料！請先在左側上傳。")
        else:
            with st.spinner("精算中..."):
                review_filename = f"審核_{p_code}.xlsx"
                quote_filename  = f"報價單_{p_code}.xlsx"
                md_filename     = f"報價單_{p_code}.md"
                
                cost, client_total = agent_ana.export_review_excel(vendors, markup_rate, p_name, REVIEW_DIR / review_filename)
                # 套用新參數
                agent_ana.export_client_quote_excel(vendors, markup_rate, p_name, p_addr, q_date.strftime("%Y/%m/%d"), q_valid, OUTPUT_DIR / quote_filename)
                md_content = agent_ana.export_markdown_quote(vendors, markup_rate, p_name, p_addr, q_date.strftime("%Y/%m/%d"), q_valid, OUTPUT_DIR / md_filename)
                
                # 上傳 Excel 至雲端
                st.info("正在同步報價單至雲端硬碟...")
                excel_url = cloud_manager.upload_file_to_drive(OUTPUT_DIR / quote_filename)
                
                # 儲存至資料庫
                db[p_code] = {
                    "category": selected_category,
                    "date": q_date.strftime("%Y/%m/%d"),
                    "project_name": p_name,
                    "project_address": p_addr,
                    "status": "報價完成",
                    "markdown_quote": md_content,
                    "excel_drive_url": excel_url
                }
                save_db(db)
                
                st.success(f"✅ 產出成功！單號：{p_code}")
                st.balloons()
                
                # 顯示網址
                st.markdown(f"🔗 **雲端下載連結：** [點此下載 Excel 報價單]({excel_url})")
                
                # 清除暫存區，確保下個案件乾淨
                for f in files:
                    f.unlink()
                st.rerun()

# === 即時預覽區 ===
st.markdown("---")
st.header("👁️ 即時預覽 (客戶前台視角)")
if current_info and current_info.get("status") == "已完成":
    md_file = BASE_DIR / current_info.get("md_path", "")
    if md_file.exists():
        with open(md_file, "r", encoding="utf-8") as f:
            st.markdown(f.read())
    else:
        st.warning("找不到對應的 Markdown 檔案。")
else:
    st.info("請先產出報價單後，即可在此預覽結果。")

# === 報價單歷史資料庫 ===
st.markdown("---")
st.header("📂 歷史報價單庫 (依分類)")

if not db:
    st.info("目前無任何紀錄。")
else:
    # 建立四個頁籤來分類歷史紀錄
    hist_tabs = st.tabs(CATEGORIES)
    
    for idx, cat in enumerate(CATEGORIES):
        with hist_tabs[idx]:
            cat_data = []
            for code, info in db.items():
                if info.get("category") == cat:
                    cat_data.append({
                        "單號": code,
                        "日期": info.get("date", "未知"),
                        "案件名稱": info.get("project_name", "未命名"),
                        "案件地址": info.get("project_address", ""),
                        "狀態": info.get("status", "未知")
                    })
            if cat_data:
                st.dataframe(cat_data, use_container_width=True)
            else:
                st.info(f"「{cat}」目前尚無報價紀錄。")
