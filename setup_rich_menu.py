# ============================================================
# AI 減肥生存管家 — Line Rich Menu 自動建立腳本
# ============================================================
# 執行方式：
#   source venv/bin/activate
#   python3 setup_rich_menu.py
# ============================================================
# 此腳本會：
#   1. 用 Pillow 生成 Rich Menu 圖片 (2500x843)
#   2. 透過 Line API 建立 Rich Menu
#   3. 上傳圖片並設定為預設選單
# ============================================================

import os
import io
import json
import logging
from dotenv import load_dotenv
import requests

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API = "https://api.line.me/v2/bot"

headers = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json",
}


def create_image() -> bytes:
    """用 Pillow 產生 Rich Menu 圖片"""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 2500, 843
    img = Image.new("RGB", (W, H), "#1a1a2e")
    draw = ImageDraw.Draw(img)

    # 尋找可用的中文字型
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",         # macOS
        "/System/Library/Fonts/STHeiti Light.ttc",    # macOS
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",       # Linux
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 60)
                font_small = ImageFont.truetype(fp, 40)
                logger.info(f"使用字型: {fp}")
                break
            except:
                continue
    if font is None:
        font = ImageFont.load_default()
        font_small = font
        logger.info("使用預設字型（無中文字型時）")

    # 三個區塊的顏色與區域
    sections = [
        # (x1, y1, x2, y2, bg_color, emoji, text, action_label)
        (0, 0, W//3, H, "#2d6a4f", "📸", "拍照分析", ""),
        (W//3, 0, 2*W//3, H, "#e76f51", "🥗", "防禦模式", ""),
        (2*W//3, 0, W, H, "#457b9d", "📊", "記錄查詢", ""),
    ]

    for x1, y1, x2, y2, color, emoji, text, _ in sections:
        draw.rectangle([x1, y1, x2, y2], fill=color)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        # 畫 emoji（用大字型）
        try:
            emoji_font = ImageFont.truetype(font_paths[0] if font_paths else "", 120)
            draw.text((cx - 40, cy - 80), emoji, fill="white", font=emoji_font)
        except:
            draw.text((cx - 40, cy - 80), emoji, fill="white", font=font)

        # 畫文字
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw//2, cy + 20), text, fill="white", font=font)

        # 畫底部小提示
        hint = "點擊執行"
        bbox2 = draw.textbbox((0, 0), hint, font=font_small)
        hw = bbox2[2] - bbox2[0]
        draw.text((cx - hw//2, y2 - 80), hint, fill="rgba(255,255,255,180)", font=font_small)

    # 分隔線
    for x in [W//3, 2*W//3]:
        draw.line([(x, 20), (x, H-20)], fill="white", width=4)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logger.info(f"Rich Menu 圖片產生完成 ({buf.tell()} bytes)")
    return buf.getvalue()


def create_rich_menu() -> str:
    """建立 Rich Menu，回傳 richMenuId"""
    menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "diet-bot-menu",
        "chatBarText": "📋 選單",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {"type": "cameraRoll", "label": "拍照分析"}
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
                "action": {"type": "message", "text": "防禦", "label": "防禦模式"}
            },
            {
                "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
                "action": {"type": "message", "text": "記錄", "label": "記錄查詢"}
            },
        ]
    }

    resp = requests.post(
        f"{LINE_API}/richmenu",
        headers=headers,
        json=menu,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"建立 Rich Menu 失敗: {resp.status_code} {resp.text[:200]}")
    rid = resp.json().get("richMenuId")
    logger.info(f"✅ Rich Menu 建立成功 (ID: {rid})")
    return rid


def upload_image(rich_menu_id: str, image_bytes: bytes):
    """上傳 Rich Menu 圖片"""
    img_headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "image/png",
    }
    resp = requests.post(
        f"{LINE_API}/richmenu/{rich_menu_id}/content",
        headers=img_headers,
        data=image_bytes,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"上傳圖片失敗: {resp.status_code} {resp.text[:200]}")
    logger.info("✅ Rich Menu 圖片上傳成功")


def set_default(rich_menu_id: str):
    """設為預設 Rich Menu"""
    resp = requests.post(
        f"{LINE_API}/richmenu/{rich_menu_id}/default",
        headers=headers,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"設定預設失敗: {resp.status_code}")
    logger.info("✅ Rich Menu 已設為預設")


def main():
    if not LINE_TOKEN:
        logger.error("❌ LINE_CHANNEL_ACCESS_TOKEN 未設定")
        return

    logger.info("=== 建立 Line Rich Menu ===")

    # 產生圖片
    image = create_image()

    # 建立 Rich Menu
    rid = create_rich_menu()

    # 上傳圖片
    upload_image(rid, image)

    # 設為預設
    set_default(rid)

    logger.info("🎉 Rich Menu 設定完成！打開 Line 看看吧")


if __name__ == "__main__":
    main()
