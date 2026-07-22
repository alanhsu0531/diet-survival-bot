# ============================================================
# AI 減肥生存管家 — Notion Database 欄位初始化腳本
# ============================================================
# 執行方式：
#   source venv/bin/activate
#   python setup_notion_db.py
#
# 這個腳本會在你的 Notion Database 中建立所有需要的欄位。
# 請先確認 .env 中的 NOTION_TOKEN 與 DATABASE_ID 已填寫正確。
# ============================================================

import os
import logging
from dotenv import load_dotenv
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
DATABASE_ID = os.getenv("DATABASE_ID", "")

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_database() -> dict:
    """取得目前 Database 的資訊"""
    url = f"{NOTION_API_URL}/databases/{DATABASE_ID}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def update_database_properties(properties: dict) -> dict:
    """更新 Database 的 Properties（欄位）"""
    url = f"{NOTION_API_URL}/databases/{DATABASE_ID}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    payload = {"properties": properties}
    resp = requests.patch(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


# ============================================================
# 要新增的欄位定義
# ============================================================
NEW_PROPERTIES = {
    # 名稱（Title）— 如果已存在就不用動
    "名稱": {"title": {}},

    # 模式（選取）
    "模式": {
        "select": {
            "options": [
                {"name": "防禦模式", "color": "green"},
                {"name": "結算模式", "color": "orange"},
            ]
        }
    },

    # 熱量（數字）
    "熱量 (大卡)": {"number": {"format": "number"}},

    # 節省熱量（數字）
    "節省熱量 (大卡)": {"number": {"format": "number"}},

    # 三大營養素（數字）
    "蛋白質 (g)": {"number": {"format": "number"}},
    "脂肪 (g)": {"number": {"format": "number"}},
    "碳水化合物 (g)": {"number": {"format": "number"}},

    # 標籤（多選）
    "標籤": {"multi_select": {"options": []}},

    # AI 回饋 / 原因（純文字）
    "AI 回饋": {"rich_text": {}},

    # 原始使用者輸入（純文字）
    "原始輸入": {"rich_text": {}},

    # ====== 新增欄位 ======

    # 餐別（選取）
    "餐別": {
        "select": {
            "options": [
                {"name": "早餐", "color": "blue"},
                {"name": "午餐", "color": "orange"},
                {"name": "晚餐", "color": "purple"},
                {"name": "點心", "color": "pink"},
            ]
        }
    },

    # 烹調方式（多選）
    "烹調方式": {
        "multi_select": {
            "options": [
                {"name": "油炸", "color": "red"},
                {"name": "煎", "color": "orange"},
                {"name": "烤", "color": "brown"},
                {"name": "蒸", "color": "blue"},
                {"name": "煮", "color": "green"},
                {"name": "炒", "color": "yellow"},
                {"name": "生食", "color": "green"},
                {"name": "燉", "color": "purple"},
            ]
        }
    },

    # 食材清單（純文字）
    "食材清單": {"rich_text": {}},

    # 記錄時間（日期）
    "記錄時間": {"date": {}},

    # ====== 公式欄位（自動計算） ======

    # 熱量等級（公式）
    "熱量等級": {
        "formula": {
            "expression": 'if(prop("熱量 (大卡)") < 400, "低 🔵", if(prop("熱量 (大卡)") < 700, "中 🟡", "高 🔴"))'
        }
    },

    # 蛋白質佔比（公式）
    "蛋白質佔比": {
        "formula": {
            "expression": 'if(prop("熱量 (大卡)") > 0, format(round(prop("蛋白質 (g)") * 4 / prop("熱量 (大卡)") * 100)) + "%", "無資料")'
        }
    },

    # 週次（公式）— 用於 Chart View 分組
    "週次": {
        "formula": {
            "expression": 'if(prop("記錄時間") != null, formatDate(prop("記錄時間"), "YYYY-ww"), "無日期")'
        }
    },
}


def main():
    # 檢查環境變數
    if not NOTION_TOKEN:
        logger.error("❌ 未設定 NOTION_TOKEN，請檢查 .env")
        return
    if not DATABASE_ID:
        logger.error("❌ 未設定 DATABASE_ID，請檢查 .env")
        return

    # 1. 先讀取目前的 Database 資訊
    logger.info("讀取目前 Database 結構…")
    try:
        db = get_database()
    except Exception as e:
        logger.error(f"❌ 無法讀取 Database：{e}")
        return

    existing_properties = db.get("properties", {})
    logger.info(f"目前已有 {len(existing_properties)} 個欄位：")
    for prop_name, prop_info in existing_properties.items():
        prop_type = prop_info.get("type", "?")
        logger.info(f"   - {prop_name} ({prop_type})")

    # 2. 合併新舊欄位（保留原有欄位 + 新增缺少的欄位）
    merged = dict(existing_properties)
    added_count = 0
    for name, definition in NEW_PROPERTIES.items():
        if name not in existing_properties:
            merged[name] = definition
            added_count += 1
            logger.info(f"   ➕ 新增欄位：{name} ({definition.get(list(definition.keys())[0], {}).get('format', list(definition.keys())[0])})")
        else:
            logger.info(f"   ✅ 欄位已存在：{name}")

    if added_count == 0:
        logger.info("所有欄位都已存在，無需更新。")
        return

    # 3. 更新 Database
    logger.info(f"\n正在新增 {added_count} 個欄位到 Database…")
    try:
        result = update_database_properties(merged)
        logger.info(f"✅ Database 更新成功！")
        updated_props = result.get("properties", {})
        logger.info(f"更新後共有 {len(updated_props)} 個欄位")
        for prop_name, prop_info in updated_props.items():
            prop_type = prop_info.get("type", "?")
            logger.info(f"   - {prop_name} ({prop_type})")
    except Exception as e:
        logger.error(f"❌ 更新失敗：{e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"   API 回應：{e.response.text[:500]}")


if __name__ == "__main__":
    main()
