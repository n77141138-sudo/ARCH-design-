import os
import json
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF
from google import genai
from google.genai import types

def init_client(api_key: str):
    return genai.Client(api_key=api_key)

def extract_images_from_pdf(pdf_path: Path):
    """將 PDF 轉為圖片列表"""
    images = []
    doc = fitz.open(str(pdf_path))
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150) # 150 DPI
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images

def parse_quote_file(file_path: Path, api_key: str) -> dict:
    """解析 JPG/PNG 或 PDF，回傳 JSON"""
    if not api_key:
        raise ValueError("請先在設定中輸入 Gemini API Key")

    client = init_client(api_key)
    
    prompt = """
    你是一個專業的室內裝修與建築工程估價精算師。
    請閱讀這份（或這幾頁）廠商報價單，並將內容提取為指定的 JSON 格式。
    
    【必填欄位說明】
    - vendor: 廠商名稱（若未註明請寫"未命名廠商"）
    - category: 判斷這是哪一種工程（例如：水電工程、油漆工程、木作工程、空調工程、拆除工程等）
    - items: 報價項目陣列
        - name: 項目名稱
        - spec: 規格/備註（若無可留空字串）
        - qty: 數量（數字，若文字無明確數量請預設為 1）
        - unit: 單位（例如：式、組、坪、口、台）
        - unit_price: 單價（數字，不含稅或小計）
        
    【特殊情境處理：對話截圖】
    - 如果圖片是 LINE 或其他通訊軟體的「對話截圖」，請綜合判斷整個上下文。
    - 若對話中，業主或設計師表示某個項目「不需要」、「取消」、「會自己處理」（例如：家具我們自己送人），**請務必在輸出的 items 中直接刪除該項目**，不要列入最終報價單。
        
    【輸出限制】
    - 嚴格回傳一個 JSON 陣列，陣列中包含一個或多個廠商物件。
    - 不要輸出任何 Markdown 標記符號（不要寫 ```json ... ```）。
    - 忽略小計與總計列，我只需要原始單價與數量的項目。
    """

    images_to_process = []
    suffix = file_path.suffix.lower()
    
    if suffix == ".pdf":
        images_to_process = extract_images_from_pdf(file_path)
    elif suffix in [".jpg", ".jpeg", ".png"]:
        images_to_process.append(Image.open(file_path))
    else:
        raise ValueError(f"不支援的格式: {suffix}")

    contents = [prompt] + images_to_process

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[:-1])
            
        parsed_json = json.loads(raw_text.strip())
        
        # 加上耗損紀錄
        tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
        return {"data": parsed_json, "tokens": tokens}
        
    except Exception as e:
        raise RuntimeError(f"AI 解析失敗: {str(e)}")


def analyze_floorplan(file_path: Path, api_key: str) -> dict:
    """分析客變圖面，推算坪數"""
    if not api_key:
        raise ValueError("請先在設定中輸入 Gemini API Key")

    client = init_client(api_key)
    
    prompt = """
    你是一個專業的建築製圖師與估價師。
    請分析這張室內設計平面圖（或客變圖）。
    
    你的任務是估算這張圖面的「室內總坪數」。
    如果圖面上有標示長寬尺寸，請根據尺寸計算。
    如果圖面上【完全沒有】標示尺寸，請找出大門的位置，並假設大門寬度為 100 公分作為基準比例尺，藉此推算整個室內空間的長寬，並換算為坪數（1坪約等於3.3平方公尺）。
    
    【回傳格式】
    嚴格回傳一個 JSON 物件，不要有任何 Markdown 標記符號：
    {
      "estimated_pings": 25.5,
      "reasoning": "簡短說明您是如何算出來的（例如：根據圖上標示的長寬計算 / 或是根據大門 100cm 比例尺推算整個空間約 8m x 10m...）"
    }
    """

    images_to_process = []
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        images_to_process = extract_images_from_pdf(file_path)
    elif suffix in [".jpg", ".jpeg", ".png"]:
        images_to_process.append(Image.open(file_path))
    else:
        raise ValueError(f"不支援的圖面格式: {suffix}")

    contents = [prompt] + images_to_process

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
        if raw_text.endswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[:-1])
            
        result = json.loads(raw_text.strip())
        
        tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
        result["tokens"] = tokens
        return result
        
    except Exception as e:
        raise RuntimeError(f"AI 圖面分析失敗: {str(e)}")
