# ============================================================
# AI 減肥生存管家 — Line Rich Menu 自動建立腳本
# ============================================================
# 執行方式：
#   source venv/bin/activate
#   python3 setup_rich_menu.py
# ============================================================

import os
import io
import logging
from dotenv import load_dotenv
import requests

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API = "https://api.line.me/v2/bot"
LINE_DATA_API = "https://api-data.line.me/v2/bot"  # 檔案上傳用不同網域

headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}


def create_image() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2500, 843
    img = Image.new("RGB", (W, H), "#0f0f23")
    draw = ImageDraw.Draw(img)

    # 字型設定
    font_large = font_mid = font_small = None
    for fp in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]:
        if os.path.exists(fp):
            try:
                font_large = ImageFont.truetype(fp, 100)
                font_mid = ImageFont.truetype(fp, 48)
                font_small = ImageFont.truetype(fp, 30)
                break
            except:
                continue
    if font_large is None:
        font_large = font_mid = font_small = ImageFont.load_default()

    # 按鈕定義
    buttons = [
        {"x": 40, "w": 790, "color": "#2ec4b6", "emoji": "📸", "title": "拍照分析",
         "sub": "拍食物，AI 自動算營養"},
        {"x": 855, "w": 790, "color": "#ff6b6b", "emoji": "🥗", "title": "防禦模式",
         "sub": "輸入菜單，推薦低卡選擇"},
        {"x": 1670, "w": 790, "color": "#6c63ff", "emoji": "📊", "title": "記錄查詢",
         "sub": "查看飲食紀錄與統計"},
    ]

    for btn in buttons:
        x, w, color = btn["x"], btn["w"], btn["color"]
        r = 30

        # 圓角矩形按鈕
        draw.rounded_rectangle([x, 30, x + w, H - 30], radius=r, fill=color)

        # icon 白色圓底
        cx = x + w // 2
        draw.ellipse([cx - 65, 180, cx + 65, 310], fill="white", width=0)
        draw.text((cx - 45, 190), btn["emoji"], fill=color, font=font_large)

        # 主標題
        b = draw.textbbox((0, 0), btn["title"], font=font_mid)
        draw.text((cx - (b[2] - b[0]) // 2, 370), btn["title"], fill="white", font=font_mid)

        # 副標題
        b2 = draw.textbbox((0, 0), btn["sub"], font=font_small)
        draw.text((cx - (b2[2] - b2[0]) // 2, 450), btn["sub"],
                  fill=(255, 255, 255, 200), font=font_small)

        # 底部提示
        draw.rounded_rectangle([cx - 100, H - 100, cx + 100, H - 65], radius=15, fill=(0, 0, 0, 30))
        draw.text((cx - 45, H - 95), "點擊 ▶", fill="white", font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def delete_all_rich_menus():
    """刪除所有舊的 Rich Menu"""
    r = requests.get(f"{LINE_API}/richmenu/list", headers=headers)
    for rm in r.json().get("richmenus", []):
        rid = rm["richMenuId"]
        resp = requests.delete(f"{LINE_API}/richmenu/{rid}", headers=headers)
        if resp.status_code in (200, 204):
            logger.info(f"🗑️ 刪除舊選單: {rm.get('name', '?')}")
    logger.info("✅ 舊選單已清除")


def create_rich_menu() -> str:
    menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "diet-bot-menu",
        "chatBarText": "📋 功能選單",
        "areas": [
            {"bounds": {"x": 40, "y": 30, "width": 790, "height": 783},
             "action": {"type": "cameraRoll", "label": "拍照分析"}},
            {"bounds": {"x": 855, "y": 30, "width": 790, "height": 783},
             "action": {"type": "message", "text": "防禦", "label": "防禦模式"}},
            {"bounds": {"x": 1670, "y": 30, "width": 790, "height": 783},
             "action": {"type": "message", "text": "記錄", "label": "記錄查詢"}},
        ]
    }
    r = requests.post(f"{LINE_API}/richmenu", headers=headers, json=menu)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"建立失敗: {r.status_code} {r.text[:200]}")
    rid = r.json()["richMenuId"]
    logger.info(f"✅ Rich Menu 建立成功")
    return rid


def upload_image(rid: str, img: bytes):
    h = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "image/png"}
    r = requests.post(f"{LINE_DATA_API}/richmenu/{rid}/content", headers=h, data=img)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"上傳圖片失敗: {r.status_code} {r.text[:200]}")
    logger.info("✅ 圖片上傳成功")


def set_default(rid: str):
    # 用 user/all 方式綁定（比 /richmenu/{id}/default 更可靠）
    r = requests.post(f"{LINE_API}/user/all/richmenu/{rid}", headers=headers)
    if r.status_code in (200, 202):
        logger.info("✅ 已設為預設")
    else:
        logger.warning(f"⚠️ 設預設失敗: {r.status_code} {r.text[:100]}")
        logger.info("請手動設定：Line Developer Console → Messaging API → Rich Menu")


def main():
    if not LINE_TOKEN:
        logger.error("❌ LINE_CHANNEL_ACCESS_TOKEN 未設定"); return
    logger.info("=== 建立 Rich Menu ===")
    delete_all_rich_menus()
    img = create_image()
    rid = create_rich_menu()
    upload_image(rid, img)
    set_default(rid)
    logger.info("🎉 完成！打開 Line 看看吧")


if __name__ == "__main__":
    main()
