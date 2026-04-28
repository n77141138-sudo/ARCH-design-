import io
import json
import os
from pathlib import Path

import gspread
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

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
    except Exception:
        # 本機環境如果沒有 secrets 檔案會拋出錯誤，直接忽略並跳到本機讀取邏輯
        pass

    # 其次從本機檔案讀取
    target_file = CREDENTIALS_FILE
    if not target_file.exists():
        target_file = BASE_DIR / "credentials.json"

    if target_file.exists():
        return service_account.Credentials.from_service_account_file(
            str(target_file), scopes=SCOPES)
    return None

def get_gspread_client():
    creds = get_credentials()
    if not creds:
        return None
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)


# === Google Sheets 資料庫操作 ===

def load_db_from_cloud():
    """從 Google Sheet 載入所有資料庫"""
    gc = get_gspread_client()
    if not gc:
        return {}
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
                except Exception:
                    pass
        return db
    except Exception as e:
        print(f"Cloud DB Load Error: {e}")
        return {}


def save_db_to_cloud(db):
    """將本地資料庫同步回 Google Sheet"""
    gc = get_gspread_client()
    if not gc:
        return False
    try:
        sh = gc.open("quotes_db")
        worksheet = sh.sheet1

        headers = ["單號", "分類", "日期", "案件名稱", "案件地址", "客戶姓名", "客戶電話", "狀態", "雲端連結", "原始資料"]
        rows = [headers]

        for code, info in db.items():
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

def _get_mime_type(filename: str) -> str:
    """根據副檔名判斷 MIME type"""
    lower = filename.lower()
    if lower.endswith('.png'):
        return "image/png"
    elif lower.endswith(('.jpg', '.jpeg')):
        return "image/jpeg"
    elif lower.endswith('.pdf'):
        return "application/pdf"
    elif lower.endswith('.xlsx'):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def get_or_create_folder(folder_name):
    """取得或建立共用的資料夾 ID"""
    drive_service = get_drive_service()
    if not drive_service:
        return None

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


def _set_public_readable(drive_service, file_id: str):
    """將 Drive 檔案設定為任何人可讀取"""
    drive_service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()


def upload_file_to_drive(file_path, folder_name="ARCH 報價單與圖面庫"):
    """上傳本機檔案至 Google Drive，回傳可公開檢視的網址"""
    drive_service = get_drive_service()
    if not drive_service:
        print("Drive Upload Error: 無法取得 Drive 憑證")
        return None

    folder_id = get_or_create_folder(folder_name)
    if not folder_id:
        print("Drive Upload Error: 無法取得或建立資料夾")
        return None

    filename = Path(file_path).name
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaFileUpload(str(file_path), mimetype=_get_mime_type(filename), resumable=True)

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        _set_public_readable(drive_service, file.get('id'))
        return file.get('webViewLink')
    except Exception as e:
        print(f"Drive Upload Error: {e}")
        return None


def upload_bytes_to_drive(file_bytes: bytes, filename: str, folder_name="ARCH 報價單與圖面庫"):
    """
    直接從記憶體 bytes 上傳至 Google Drive（適用於 Streamlit Cloud 環境）。
    避免在雲端伺服器上寫本機檔案的問題。
    回傳可公開檢視的網址，失敗時回傳 None。
    """
    drive_service = get_drive_service()
    if not drive_service:
        print("Drive Upload (bytes) Error: 無法取得 Drive 憑證")
        return None

    folder_id = get_or_create_folder(folder_name)
    if not folder_id:
        print("Drive Upload (bytes) Error: 無法取得或建立資料夾")
        return None

    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=_get_mime_type(filename), resumable=True)

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        _set_public_readable(drive_service, file.get('id'))
        return file.get('webViewLink')
    except Exception as e:
        print(f"Drive Upload (bytes) Error: {e}")
        return None
