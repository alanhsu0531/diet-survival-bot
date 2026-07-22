# ============================================================
# 更新 Notion 公式欄位（簡化版本）
# ============================================================
# 執行方式：source venv/bin/activate && python3 add_formulas.py
# ============================================================
import os, logging, requests
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
url = f"https://api.notion.com/v1/databases/{DATABASE_ID}"
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# 逐一新增公式欄位
formulas = {
    "熱量等級": {
        "formula": {
            "expression": 'if(prop("熱量 (大卡)") < 400, "低", if(prop("熱量 (大卡)") < 700, "中", "高"))'
        }
    },
    "蛋白質佔比": {
        "formula": {
            "expression": 'if(prop("熱量 (大卡)") > 0, format(round(prop("蛋白質 (g)") * 4 / prop("熱量 (大卡)") * 100)) + "%", "")'
        }
    },
    "週次": {
        "formula": {
            "expression": 'if(prop("記錄時間") != null, formatDate(prop("記錄時間"), "YYYY-ww"), "")'
        }
    },
}

for name, definition in formulas.items():
    resp = requests.patch(url, headers=headers, json={"properties": {name: definition}})
    if resp.status_code in (200, 201):
        logger.info(f"✅ {name} 新增成功")
    else:
        logger.error(f"❌ {name} 失敗: {resp.status_code} {resp.text[:200]}")
