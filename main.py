# ============================================================
# AI 減肥生存管家 — Webhook 伺服器 (main.py)
# ============================================================
# 啟動方式：
#   uvicorn main:app --reload --port 8000
#
# 注意：請先在 .env 檔案中設定以下環境變數：
#   LINE_CHANNEL_SECRET=你的頻道密鑰
#   LINE_CHANNEL_ACCESS_TOKEN=你的頻道存取權杖
# ============================================================

import os
import base64
import json
import io
import logging
from typing import Optional

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
)

# ---------- 匯入自訂模組 ----------
from typing import Optional

from ai_processor import process_with_ai, clean_tags
from notion_writer import create_notion_page

# ---------- 載入環境變數 ----------
load_dotenv()

# 請在 .env 檔案中設定以下兩個變數
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# ---------- 建立 FastAPI 應用程式 ----------
app = FastAPI(title="AI 減肥生存管家")

# ---------- 初始化 Line SDK ----------
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(channel_secret=LINE_CHANNEL_SECRET)

# ---------- 日誌設定 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# 工具函數：從 Line 伺服器下載圖片並轉為 Base64
# ============================================================
def download_image_to_base64(message_id: str) -> Optional[str]:
    """
    使用 Line Messaging API 下載圖片，壓縮後轉為 Base64 回傳。
    壓縮目的：減少 API 傳輸大小、加快 OpenRouter 回應速度。
    """
    try:
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            content = blob_api.get_message_content(message_id)
            if isinstance(content, bytes):
                image_bytes = content
            else:
                image_bytes = content.read()

        # 使用 Pillow 壓縮圖片，限制最長邊 1024px、JPEG 品質 85
        if HAS_PILLOW:
            img = Image.open(io.BytesIO(image_bytes))
            max_dim = 1024
            w, h = img.size
            if w > max_dim or h > max_dim:
                ratio = min(max_dim / w, max_dim / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buffer = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=85)
            image_bytes = buffer.getvalue()
            logger.info(
                f"圖片壓縮完成 ({w}x{h} → {img.size[0]}x{img.size[1]}, "
                f"{len(image_bytes)} bytes)"
            )
        else:
            logger.info(f"圖片未壓縮 ({len(image_bytes)} bytes)")

        base64_str = base64.b64encode(image_bytes).decode("utf-8")
        logger.info(f"圖片 Base64 轉換完成 ({len(base64_str)} chars)")
        return base64_str
    except Exception as e:
        logger.error(f"下載圖片失敗: {e}")
        return None


# ============================================================
# Webhook 端點 — POST /webhook
# ============================================================
@app.post("/webhook")
async def webhook(request: Request):
    """
    接收 Line 伺服器推送的 Webhook 事件。

    流程：
      1. 取得 X-Line-Signature 進行簽章驗證（確保請求來自 Line）
      2. 將請求內容轉發給 Line SDK 的 WebhookHandler 處理
    """
    # 取得簽章（Line 用於驗證請求來源的 Header）
    signature = request.headers.get("X-Line-Signature", "")

    # 讀取原始的請求 Body（須為 bytes）
    body = await request.body()

    logger.info(f"收到 Webhook 請求，signature={signature[:20]}...")

    try:
        # 交由 handler 進行簽章驗證與事件分發
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        # 簽章不匹配，可能是偽造請求
        logger.warning("簽章驗證失敗！可能的偽造請求！")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return PlainTextResponse("OK")


# ============================================================
# MessageEvent 處理器 — 處理使用者傳送的訊息
# ============================================================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent) -> None:
    """
    處理使用者傳送的文字訊息（TextMessage）。

    情境與觸發關鍵字：
      - 若訊息以 '防禦'、'菜單'、'menu' 開頭 → 進入防禦模式（菜單破譯）
      - 否則 → 進入結算模式（毒舌紀錄）

    流程：
      1. 將使用者文字傳送給 AI 模組進行分析
      2. 將 AI 回傳的 JSON 結果寫入 Notion 資料庫
      3. 回覆使用者分析結果
    """
    user_text = event.message.text.strip()
    reply_token = event.reply_token
    user_id = event.source.user_id

    logger.info(f"收到文字訊息 (user={user_id}): {user_text[:50]}...")

    # 判斷模式：簡易關鍵字觸發
    is_defense_mode = any(
        keyword in user_text for keyword in ["防禦", "菜單", "menu", "Menu"]
    )

    # 呼叫 AI 處理核心，取得結構化 JSON 結果
    # 【注意】第二個參數 image_base64 傳入 None，表示無圖片
    try:
        ai_result = process_with_ai(
            user_text=user_text,
            image_base64=None,
            defense_mode=is_defense_mode,
        )
        logger.info(f"AI 分析結果: {json.dumps(ai_result, ensure_ascii=False)}")

        # 對 AI 回傳的標籤資料進行清洗
        if "tags" in ai_result and isinstance(ai_result["tags"], list):
            ai_result["tags"] = clean_tags(ai_result["tags"])

        # 寫入 Notion 資料庫（非同步操作以同步方式執行）
        try:
            create_notion_page(ai_result)
            logger.info("Notion 寫入成功")
        except Exception as e:
            logger.error(f"Notion 寫入失敗: {e}")

        # 整理回覆訊息
        reply_text = format_reply_message(ai_result, is_defense_mode)

    except Exception as e:
        logger.error(f"AI 處理發生錯誤: {e}")
        reply_text = "哎呀，我的大腦短路了一下 😵，請再傳一次試試看！"

    # 透過 Line API 回覆使用者
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event: MessageEvent) -> None:
    """
    處理使用者傳送的圖片訊息（ImageMessage）。
    """
    reply_token = event.reply_token
    user_id = event.source.user_id
    message_id = event.message.id

    logger.info(f"收到圖片訊息 (user={user_id})")

    # 使用同步方式下載圖片
    image_base64 = download_image_to_base64(message_id)

    if image_base64 is None:
        reply_text = "圖片處理失敗了 😢，請重新上傳一次！"
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )
        return

    # 呼叫 AI 處理核心（結算模式 + 有圖片）
    try:
        ai_result = process_with_ai(
            user_text="請分析這張照片中的食物",
            image_base64=image_base64,
            defense_mode=False,  # 圖片預設走結算模式
        )
        logger.info(f"AI 圖片分析結果: {json.dumps(ai_result, ensure_ascii=False)}")

        # 清洗標籤
        if "tags" in ai_result and isinstance(ai_result["tags"], list):
            ai_result["tags"] = clean_tags(ai_result["tags"])

        # 寫入 Notion
        try:
            create_notion_page(ai_result)
            logger.info("Notion 寫入成功")
        except Exception as e:
            logger.error(f"Notion 寫入失敗: {e}")

        reply_text = format_reply_message(ai_result, defense_mode=False)

    except Exception as e:
        logger.error(f"AI 圖片處理錯誤: {e}")
        reply_text = "分析圖片時好像出了點問題 🤔，再試一次吧！"

    # 回覆使用者
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


# ============================================================
# 回覆訊息格式化
# ============================================================
def format_reply_message(data: dict, defense_mode: bool) -> str:
    """
    將 AI 回傳的 JSON 資料轉換為人類可讀的文字回覆。

    Args:
        data: AI 分析結果字典
        defense_mode: 是否為防禦模式

    Returns:
        格式化後的中文回覆字串
    """
    if defense_mode:
        # ---------- 防禦模式回覆格式 ----------
        lines = ["🥗 防禦模式 · 菜單破譯報告 🥗", "=" * 30]
        if "original_menu" in data:
            lines.append(f"📋 原始菜單：{data['original_menu']}")
        if "recommendation" in data:
            lines.append(f"✅ 推薦選擇：{data['recommendation']}")
        if "reason" in data:
            lines.append(f"💡 原因：{data['reason']}")
        if "calories_saved" in data:
            lines.append(f"🔥 節省熱量：約 {data['calories_saved']} 大卡")
        if "tags" in data and data["tags"]:
            tags_str = "、".join(data["tags"])
            lines.append(f"🏷️ 標籤：{tags_str}")
    else:
        # ---------- 結算模式回覆格式 ----------
        lines = ["🍽️ 結算模式 · 毒舌紀錄 🍽️", "=" * 30]
        if "dish_name" in data:
            lines.append(f"🥘 辨識餐點：{data['dish_name']}")
        if "calories" in data:
            lines.append(f"🔥 估算熱量：{data['calories']} 大卡")
        if "protein" in data:
            lines.append(f"🥩 蛋白質：{data['protein']}g")
        if "fat" in data:
            lines.append(f"🧈 脂肪：{data['fat']}g")
        if "carbs" in data:
            lines.append(f"🍚 碳水化合物：{data['carbs']}g")
        if "comment" in data:
            lines.append(f"\n💬 毒舌回饋：\n{data['comment']}")
        if "tags" in data and data["tags"]:
            tags_str = "、".join(data["tags"])
            lines.append(f"\n🏷️ 標籤：{tags_str}")

    return "\n".join(lines)


# ============================================================
# 健康檢查端點（UptimeRobot 使用 HEAD 請求）
# ============================================================
@app.get("/health")
@app.head("/health")
async def health_check():
    return {"status": "ok", "service": "AI 減肥生存管家"}


# ============================================================
# 直接執行時啟動 uvicorn
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
