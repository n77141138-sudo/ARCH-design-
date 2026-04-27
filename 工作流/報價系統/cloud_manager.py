import json
import os
from pathlib import Path
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import streamlit as st

# 設定檔案路徑
BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "arch-quote-system-5ab37e7fe80d.json"

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_credentials():
    # 優先從 Streamlit Secrets 讀取 (雲端部屬用)
    try:
        if "gcp_service_account" in st.secrets:
            return service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=SCOPES)
    except:
        # 本機環境如果沒有 secrets 檔案會拋出錯誤，直接忽略並跳到本機讀取邏輯
        pass
    
    # 其次從本機檔案讀取
    target_file = CREDENTIALS_FILE
    if not target_file.exists():
        target_file = BASE_DIR / "credentials.json"
    
    if target_file.exists():
        return service_account.Credentials.from_service_account_file(
            target_file, scopes=SCOPES)
    return None

def get_gspread_client():
    creds = get_credentials()
    if not creds: return None
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_credentials()
    if not creds: return None
    return build('drive', 'v3', credentials=creds)

# === Google Sheets 資料庫操作 ===
def load_db_from_cloud():
    """從 Google Sheet 載入所有資料庫"""
    gc = get_gspread_client()
    if not gc: return {}
    try:
        sh = gc.open("quotes_db")
        worksheet = sh.sheet1
        records = worksheet.get_all_records()
        
        db = {}
        for row in records:
            code = row.get("單號", "")
            raw_json = row.get("原始資料", "{}")
            if code:
                try:
                    db[str(code)] = json.loads(raw_json)
                except:
                    pass
        return db
    except Exception as e:
        print(f"Cloud DB Load Error: {e}")
        return {}

def save_db_to_cloud(db):
    """將本地資料庫同步回 Google Sheet"""
    gc = get_gspread_client()
    if not gc: return False
    try:
        sh = gc.open("quotes_db")
        worksheet = sh.sheet1
        
        # 準備要寫入的資料矩陣 (增加更多人類可讀的欄位)
        headers = ["單號", "分類", "日期", "案件名稱", "案件地址", "客戶姓名", "客戶電話", "狀態", "雲端連結", "原始資料"]
        rows = [headers]
        
        for code, info in db.items():
            # 優先取得下載連結 (可能是 Excel 或是圖面)
            drive_url = info.get("excel_drive_url") or info.get("floorplan_drive_url") or ""
            
            rows.append([
                str(code),
                info.get("category", ""),
                info.get("date", ""),
                info.get("project_name", ""),
                info.get("project_address", ""),
                info.get("client_name", ""),
                info.get("client_phone", info.get("phone", "")),
                info.get("status", ""),
                drive_url,
                json.dumps(info, ensure_ascii=False)
            ])
            
        worksheet.clear()
        worksheet.update(rows)
        return True
    except Exception as e:
        print(f"Cloud DB Save Error: {e}")
        return False

# === Google Drive 檔案操作 ===
def get_or_create_folder(folder_name):
    """取得或建立共用的資料夾 ID"""
    drive_service = get_drive_service()
    if not drive_service: return None
    
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        return items[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def upload_file_to_drive(file_path, folder_name="ARCH 報價單與圖面庫"):
    """上傳檔案至 Google Drive，並設定權限為任何人可檢視，回傳檢視網址"""
    drive_service = get_drive_service()
    if not drive_service: return None
    
    folder_id = get_or_create_folder(folder_name)
    if not folder_id: return None
    
    file_metadata = {
        'name': Path(file_path).name,
        'parents': [folder_id]
    }
    
    # 簡單偵測 MIME type
    mime_type = "application/octet-stream"
    if str(file_path).endswith('.xlsx'):
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif str(file_path).endswith(('.jpg', '.jpeg')):
        mime_type = "image/jpeg"
    elif str(file_path).endswith('.png'):
        mime_type = "image/png"
    elif str(file_path).endswith('.pdf'):
        mime_type = "application/pdf"
        
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    
    try:
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        
        # 設定權限為任何人可讀取
        drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        print(f"Drive Upload Error: {e}")
        return None
