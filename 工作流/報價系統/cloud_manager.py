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
    """取得 Google 憑證，優先從 Streamlit Secrets 讀取，其次從本機檔案。"""
    # 優先從 Streamlit Secrets 讀取 (雲端部屬用)
    try:
        if "gcp_service_account" in st.secrets:
            # 必須轉成純 dict，st.secrets 回傳的 AttrDict 可能導致 SDK 解析失敗
            cred_info = dict(st.secrets["gcp_service_account"])
            return service_account.Credentials.from_service_account_info(
                cred_info, scopes=SCOPES)
    except Exception as e:
        print(f"Streamlit Secrets 讀取失敗: {e}")
        # 繼續嘗試本機檔案

    # 其次從本機 JSON 檔案讀取
    target_file = CREDENTIALS_FILE
    if not target_file.exists():
        target_file = BASE_DIR / "credentials.json"

    if target_file.exists():
        try:
            return service_account.Credentials.from_service_account_file(
                str(target_file), scopes=SCOPES)
        except Exception as e:
            print(f"本機憑證讀取失敗: {e}")

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

def _get_or_create_images_sheet(sh):
    """取得或建立 images 分頁（存放 base64 圖片資料）"""
    try:
        return sh.worksheet("images")
    except Exception:
        ws = sh.add_worksheet(title="images", rows=500, cols=3)
        ws.update([["單號", "圖片類型", "base64資料"]])
        return ws


def load_db_from_cloud():
    """從 Google Sheet 載入所有資料庫，並合併 images 分頁的圖片資料"""
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

        # 合併 images 分頁的 base64 圖片
        try:
            img_ws = sh.worksheet("images")
            img_records = img_ws.get_all_records()
            for row in img_records:
                code = str(row.get("單號", ""))
                b64 = row.get("base64資料", "")
                img_type = row.get("圖片類型", "floorplan_b64")
                if code and b64 and code in db:
                    db[code][img_type] = b64
        except Exception:
            pass  # images 分頁不存在也沒關係

        return db
    except Exception as e:
        print(f"Cloud DB Load Error: {e}")
        return {}


def save_db_to_cloud(db):
    """將本地資料庫同步回 Google Sheet，base64 圖片另存 images 分頁"""
    gc = get_gspread_client()
    if not gc:
        return False
    try:
        sh = gc.open("quotes_db")
        worksheet = sh.sheet1

        headers = ["單號", "分類", "日期", "案件名稱", "案件地址", "客戶姓名", "客戶電話", "狀態", "雲端連結", "原始資料"]
        rows = [headers]
        # 收集需要另存的圖片資料
        image_rows = [["單號", "圖片類型", "base64資料"]]
        IMAGE_KEYS = {"floorplan_b64"}

        for code, info in db.items():
            drive_url = info.get("excel_drive_url") or info.get("floorplan_drive_url") or ""

            # 從主記錄中移除大型 b64 欄位，避免超過 Google Sheets 50,000 字元限制
            info_for_sheet = {k: v for k, v in info.items() if k not in IMAGE_KEYS}

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
                json.dumps(info_for_sheet, ensure_ascii=False)
            ])

            # 收集圖片
            for img_key in IMAGE_KEYS:
                b64_val = info.get(img_key, "")
                if b64_val:
                    image_rows.append([str(code), img_key, b64_val])

        worksheet.clear()
        worksheet.update(rows)

        # 寫入 images 分頁（base64 圖片資料）
        if len(image_rows) > 1:  # 有圖片才寫
            img_ws = _get_or_create_images_sheet(sh)
            img_ws.clear()
            img_ws.update(image_rows)

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
    """
    取得資料夾 ID。
    優先檢查 DRIVE_FOLDER_ID 環境變數（Secrets 設定），
    邏免 Service Account 無個人儲存配額的限制。
    """
    # 優先從 Streamlit Secrets 或環境變數取得使用者指定的資料夾 ID
    try:
        folder_id = st.secrets.get("DRIVE_FOLDER_ID", "") or os.environ.get("DRIVE_FOLDER_ID", "")
        if folder_id:
            return folder_id.strip()
    except Exception:
        folder_id = os.environ.get("DRIVE_FOLDER_ID", "")
        if folder_id:
            return folder_id.strip()

    # fallback: 嘗試在 Service Account 的 Drive 中建立資料夾（可能因配額問題失敗）
    drive_service = get_drive_service()
    if not drive_service:
        return None

    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive_service.files().list(
        q=query, spaces='drive', fields='files(id, name)'
    ).execute()
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
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        _set_public_readable(drive_service, file.get('id'))
        return file.get('webViewLink')
    except Exception as e:
        print(f"Drive Upload Error: {e}")
        return None


def upload_bytes_to_drive(file_bytes: bytes, filename: str, folder_name="ARCH 報價單與圖面庫"):
    """
    直接從記憶體 bytes 上傳至 Google Drive（適用於 Streamlit Cloud 環境）。
    回傳 (url, error_message)：
      - 成功時：(webViewLink, None)
      - 失敗時：(None, 錯誤說明字串)
    """
    drive_service = get_drive_service()
    if not drive_service:
        msg = "無法取得 Google Drive 憑證。請確認 Streamlit Secrets 中的 [gcp_service_account] 已正確設定。"
        print(f"Drive Upload Error: {msg}")
        return None, msg

    folder_id = get_or_create_folder(folder_name)
    if not folder_id:
        msg = "無法在 Google Drive 建立或找到目標資料夾，請確認服務帳號有 Drive 存取權限。"
        print(f"Drive Upload Error: {msg}")
        return None, msg

    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=_get_mime_type(filename), resumable=True)

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        _set_public_readable(drive_service, file.get('id'))
        return file.get('webViewLink'), None
    except Exception as e:
        msg = str(e)
        print(f"Drive Upload Error: {msg}")
        return None, msg
