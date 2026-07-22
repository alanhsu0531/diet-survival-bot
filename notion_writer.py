# ============================================================
# AI 減肥生存管家 — Notion 資料庫寫入 (notion_writer.py)
# ============================================================
#
# 本模組負責將 AI 分析完成的 JSON 結果寫入 Notion Database。
#
# 使用 Notion API (v1) 的 Create Page 端點：
#   POST https://api.notion.com/v1/pages
#
# 注意：請先在 .env 檔案中設定以下環境變數：
#   NOTION_TOKEN=你的 Notion Integration Token
#   DATABASE_ID=你的 Notion Database ID（不含連字號的 32 字元 UUID）
# ============================================================

import os
import json
import logging
from typing import Any, Optional

from dotenv import load_dotenv
import requests

# 載入 .env 環境變數（讓獨立執行時也能讀取）
load_dotenv()

# ---------- 日誌設定 ----------
logger = logging.getLogger(__name__)

# ---------- Notion API 設定 ----------
# 【注意】請在 .env 檔案中設定以下兩個變數
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
DATABASE_ID = os.getenv("DATABASE_ID", "")

# Notion API 端點（建立 Page）
NOTION_API_URL = "https://api.notion.com/v1/pages"

# Notion API 版本（建議使用最新的穩定版本）
NOTION_VERSION = "2022-06-28"


def safe_int(value: Any) -> Optional[int]:
    """安全地將值轉為整數，若無法轉換則回傳 None"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def safe_float(value: Any) -> Optional[float]:
    """安全地將值轉為浮點數，若無法轉換則回傳 None"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ============================================================
# Notion 屬性值建構函數
# ============================================================
def build_notion_properties(data: dict[str, Any]) -> dict[str, Any]:
    """
    將 AI 分析結果轉換為 Notion Database Page 的屬性格式。

    Notion API 的屬性格式因類型而異，常見的欄位類型包含：
      - title: 標題
      - rich_text: 多行文字
      - number: 數字
      - multi_select: 多選標籤
      - select: 單選
      - date: 日期

    以下是根據我們 AI 回傳的 JSON 結構所設計的對應。
    【注意】請根據你實際的 Notion Database 欄位設定，修改下方的對應邏輯。

    Args:
        data: AI 分析結果字典（已由 ai_processor 清理過）

    Returns:
        符合 Notion API 格式的 properties 字典
    """
    properties: dict[str, Any] = {}

    # ---- 標題欄位 ----
    # 結算模式用 dish_name，防禦模式用 original_menu
    title_text = data.get("dish_name") or data.get("original_menu") or "未知餐點"
    properties["名稱"] = {
        "title": [
            {
                "text": {"content": title_text[:100]},  # Notion 標題長度限制
            }
        ]
    }

    # ---- 模式 ----
    mode = data.get("mode", "")
    mode_name = {"defense": "防禦模式", "water": "飲水"}.get(mode, "結算模式")
    properties["模式"] = {"select": {"name": mode_name}}

    # ---- 熱量（數字） ----
    calories = safe_int(data.get("calories"))
    if calories is not None:
        properties["熱量 (大卡)"] = {"number": calories}
    calories_saved = safe_int(data.get("calories_saved"))
    if calories_saved is not None:
        if data.get("mode") == "water":
            properties["水量 (ml)"] = {"number": calories_saved}
        else:
            properties["節省熱量 (大卡)"] = {"number": calories_saved}

    # ---- 三大營養素（數字） ----
    for nutrient_key, nutrient_label in [
        ("protein", "蛋白質 (g)"),
        ("fat", "脂肪 (g)"),
        ("carbs", "碳水化合物 (g)"),
    ]:
        nutrient_val = safe_float(data.get(nutrient_key))
        if nutrient_val is not None:
            properties[nutrient_label] = {"number": nutrient_val}

    # ---- 標籤（多選 Multi-select） ----
    if "tags" in data and isinstance(data["tags"], list):
        properties["標籤"] = {
            "multi_select": [
                {"name": tag.strip()[:50]}  # 預防過長標籤
                for tag in data["tags"]
                if tag.strip()
            ]
        }

    # ---- 評論 / 原因（純文字） ----
    comment_text = data.get("comment") or data.get("reason") or ""
    if comment_text:
        properties["AI 回饋"] = {
            "rich_text": [
                {
                    "text": {"content": comment_text[:2000]},  # 預防過長
                }
            ]
        }

    # ---- 原始輸入（純文字） ----
    original_input = data.get("original_menu") or ""
    if not original_input and "dish_name" in data:
        original_input = data.get("dish_name", "")
    if original_input:
        properties["原始輸入"] = {
            "rich_text": [
                {
                    "text": {"content": original_input[:2000]},
                }
            ]
        }

    # ---- 餐別（選取） ----
    meal_type = data.get("meal_type")
    if meal_type and meal_type in ("早餐", "午餐", "晚餐", "點心"):
        properties["餐別"] = {"select": {"name": meal_type}}

    # ---- 烹調方式（多選） ----
    methods = data.get("cooking_methods")
    if methods and isinstance(methods, list):
        valid_methods = [m for m in methods if m.strip()]
        if valid_methods:
            properties["烹調方式"] = {
                "multi_select": [{"name": m.strip()[:20]} for m in valid_methods]
            }

    # ---- 食材清單（純文字） ----
    ingredients = data.get("ingredients")
    if ingredients:
        properties["食材清單"] = {
            "rich_text": [{"text": {"content": ingredients[:2000]}}]
        }

    # ---- 記錄時間（日期） ----
    from datetime import datetime, timezone
    properties["記錄時間"] = {
        "date": {"start": datetime.now(timezone.utc).isoformat()}
    }

    return properties


# ============================================================
# 建立 Notion Database Page
# ============================================================
def create_notion_page(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    在 Notion Database 中建立一個新的 Page，寫入 AI 分析結果。

    使用 Notion API 的 Create Page 端點：
      POST https://api.notion.com/v1/pages

    請求 Header 需要：
      - Authorization: Bearer {NOTION_TOKEN}
      - Content-Type: application/json
      - Notion-Version: 2022-06-28

    Body 格式：
      {
        "parent": { "database_id": "你的 DATABASE_ID" },
        "properties": { ... }
      }

    Args:
        data: AI 分析結果字典（包含 mode, tags 等欄位）

    Returns:
        Notion API 回傳的 Page 物件（dict），若失敗則回傳 None

    Raises:
        會記錄錯誤日誌但不會拋出例外，避免影響 Webhook 回應
    """
    # 檢查必要的環境變數
    if not NOTION_TOKEN:
        logger.error("未設定 NOTION_TOKEN，請在 .env 檔案中填寫")
        return None
    if not DATABASE_ID:
        logger.error("未設定 DATABASE_ID，請在 .env 檔案中填寫")
        return None

    # 建構 request payload
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    # 轉換資料為 Notion 屬性格式
    properties = build_notion_properties(data)

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
    }

    logger.info(
        f"寫入 Notion Database (DATABASE_ID={DATABASE_ID[:12]}...)"
    )
    logger.debug(f"Notion Payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")

    try:
        response = requests.post(
            NOTION_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )

        # 檢查 HTTP 狀態
        if response.status_code in (200, 201):
            result = response.json()
            page_id = result.get("id", "unknown")
            logger.info(f"Notion Page 建立成功！Page ID: {page_id}")
            return result
        else:
            logger.error(
                f"Notion API 錯誤 (status={response.status_code}): "
                f"{response.text[:500]}"
            )
            return None

    except requests.exceptions.Timeout:
        logger.error("Notion API 請求超時")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("無法連線到 Notion API，請檢查網路連線")
        return None
    except Exception as e:
        logger.error(f"Notion API 未知錯誤: {e}")
        return None


# ============================================================
# 測試用：直接執行本檔案時進行簡單測試
# ============================================================
if __name__ == "__main__":
    # 測試資料（模擬 AI 結算模式的輸出）
    test_data = {
        "mode": "settlement",
        "dish_name": "招牌排骨便當",
        "calories": 850,
        "protein": 35,
        "fat": 40,
        "carbs": 80,
        "comment": "這個排骨便當的熱量直接讓你今天的努力白費了 🙃 炸排骨吸油像海綿，配菜只有一小撮高麗菜，下次請選滷雞腿便當好嗎？",
        "tags": ["便當", "高熱量", "油炸", "少蔬菜"],
    }

    # 執行寫入測試
    result = create_notion_page(test_data)
    if result:
        print("✅ Notion 測試寫入成功！")
        print(f"   Page ID: {result.get('id')}")
    else:
        print("❌ Notion 測試寫入失敗！請檢查環境變數與網路連線。")
