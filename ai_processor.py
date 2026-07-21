# ============================================================
# AI 減肥生存管家 — AI 處理核心 (ai_processor.py)
# ============================================================
#
# 本模組負責：
#   1. 呼叫本地 OmniRoute 伺服器（相容於 OpenAI API 格式）
#   2. 提供兩種 AI 分析模式：
#      A. 防禦模式（菜單破譯）— 搭配照片與文字給出低卡建議
#      B. 結算模式（毒舌紀錄）— 辨識便當、估算營養、毒舌評語
#   3. 使用正規表達式清洗 AI 生成的中文標籤
#
# OmniRoute 預設位址：http://localhost:20128/v1
# 若需要修改，請調整下方的 OMNIROUTE_BASE_URL
# ============================================================

import os
import re
import json
import time
import logging
from typing import Any, Optional

from dotenv import load_dotenv
import requests

# 載入 .env 環境變數
load_dotenv()

# ---------- 日誌設定 ----------
logger = logging.getLogger(__name__)

# ---------- OmniRoute 伺服器設定 ----------
# 【注意】如果你的 OmniRoute 伺服器在其他位址或連接埠，
# 請修改下方的網址，或設定環境變數 OMNIROUTE_BASE_URL
OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128/v1")

# 建議使用的模型名稱（OmniRoute combo 路由模式）
# 可用的模型名稱範例：auto/best-fast, auto/best-chat, auto/best-vision, auto/best-coding
# 請依你的 OmniRoute 設定調整
MODEL_NAME = os.getenv("AI_MODEL", "auto/best-fast")


# ============================================================
# 工具函數：使用 Regex 清洗中文標籤
# ============================================================
def clean_tags(tags: list[str]) -> list[str]:
    """
    清洗 AI 生成的中文分類標籤，移除詞性標記。

    問題描述：
      AI 傳回的中文標籤有時會附帶詞性標記，例如：
        "牛肉麵(名詞)"、"跑步(動詞)"、"美味(形容詞)"
      這些括號內的詞性資訊對後續儲存與展示沒有幫助，需要清除。

    本函數使用正規表達式移除所有「中文括號（）及其內部內容」。
    同時移除前後空白，並過濾空字串。

    Regex 說明：
      模式：\s*[（(][^)）]*[）)]\s*
      - \s*            ：匹配括號前後的空白
      - [（(]      ：匹配全形（或半形 (
      - [^)）]*    ：匹配非 ) 或 ）的任何字元
      - [）)]      ：匹配全形）或半形 )

    Args:
        tags: 原始標籤列表，例如 ["牛肉麵(名詞)", "健康(形容詞)", "跑步"]

    Returns:
        清洗後的標籤列表，例如 ["牛肉麵", "健康", "跑步"]

    Example:
        >>> clean_tags(["牛肉麵(名詞)", " 美味(形容詞) ", "跑步", "低卡"])
        ['牛肉麵', '美味', '跑步', '低卡']
    """
    # 此正規表達式會匹配全形（）與半形 () 及其內部所有文字
    pattern = re.compile(r"\s*[（(][^)）]*[）)]\s*")

    cleaned = []
    for tag in tags:
        # 移除詞性標記
        cleaned_tag = pattern.sub("", tag)
        # 移除前後空白
        cleaned_tag = cleaned_tag.strip()
        # 過濾空字串
        if cleaned_tag:
            cleaned.append(cleaned_tag)

    logger.debug(f"標籤清洗完成：{tags} → {cleaned}")
    return cleaned


# ============================================================
# 建構 AI 系統提示詞（System Prompt）
# ============================================================
def build_system_prompt(defense_mode: bool) -> str:
    """
    根據模式建構對應的系統提示詞，引導 AI 以指定的 JSON 格式回覆。

    Args:
        defense_mode: True 為防禦模式，False 為結算模式

    Returns:
        系統提示詞字串
    """
    if defense_mode:
        # ---------- 防禦模式：菜單破譯 ----------
        return """你是一位毒舌但實用的減肥營養師。使用者會傳送餐廳菜單或熱量文字，
請你分析並推薦低卡、高蛋白的餐點組合。

請務必以以下的 JSON 格式回覆（只能回傳 JSON，不要加 Markdown 程式碼區塊）：

{
    "mode": "defense",
    "original_menu": "使用者原始輸入的菜單內容",
    "recommendation": "你推薦的最佳低卡選擇，例如：嫩雞胸肉沙拉 + 無糖綠茶",
    "reason": "簡短說明推薦原因（50字以內）",
    "calories_saved": "相比原始選擇可節省的熱量估計（整數，單位大卡）",
    "tags": ["相關標籤，例如低卡", "高蛋白", "增肌"]
}

注意事項：
- 標籤 (tags) 請給出 2~4 個中文關鍵字
- 標籤中【不要附加詞性標記】，例如寫「低卡」而非「低卡(形容詞)」
- 總熱量節省請給整數"""
    else:
        # ---------- 結算模式：毒舌紀錄 ----------
        return """你是一位毒舌且幽默的減肥教練。使用者會傳送便當或餐點的照片與說明，
請你辨識食物內容、估算營養素，並給予「毒舌」或「鼓勵」的評語。

請務必以以下的 JSON 格式回覆（只能回傳 JSON，不要加 Markdown 程式碼區塊）：

{
    "mode": "settlement",
    "dish_name": "辨識出的餐點名稱，例如：招牌三寶便當",
    "calories": 850,
    "protein": 35,
    "fat": 40,
    "carbs": 80,
    "comment": "毒舌或鼓勵的評語（30~80字，語氣幽默風趣，帶一點機車但不會讓人討厭）",
    "tags": ["便當", "高熱量", "油炸", "少蔬菜"]
}

注意事項：
- 熱量與三大營養素請盡量合理估算，單位分別為大卡與公克 (g)
- 標籤 (tags) 請給出 2~4 個中文關鍵字，描述該餐點的健康特性
- 標籤中【不要附加詞性標記】，例如寫「高熱量」而非「高熱量(名詞)」
- comment 要保持毒蛇風格，但最後可以給一點建設性的建議"""


# ============================================================
# 建構使用者提示詞
# ============================================================
def build_user_message(
    user_text: str, image_base64: Optional[str], defense_mode: bool
) -> list[dict[str, Any]]:
    """
    建構發送給 AI 的使用者訊息內容。
    支援純文字與圖片+文字的混合輸入。

    Args:
        user_text: 使用者輸入的文字
        image_base64: 圖片的 Base64 編碼字串（可為 None）
        defense_mode: 是否為防禦模式（僅影響文字描述中的提示）

    Returns:
        OpenAI API 格式的 messages 內容列表
    """
    # 根據模式決定輔助描述文字
    if defense_mode:
        text_prefix = "請幫我分析這份菜單，給我低卡建議：\n\n"
    else:
        text_prefix = "請幫我結算這個便當的營養與熱量：\n\n"

    content: list[dict[str, Any]] = []

    # 如果有圖片，以多模態格式附加
    if image_base64:
        content.append({
            "type": "text",
            "text": f"{text_prefix}{user_text}",
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
            },
        })
    else:
        content.append({
            "type": "text",
            "text": f"{text_prefix}{user_text}",
        })

    return content


# ============================================================
# 呼叫 OmniRoute 伺服器（OpenAI 相容 API）
# ============================================================
def call_omniroute(
    messages: list[dict[str, Any]],
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """
    向本地 OmniRoute 伺服器發送聊天完成請求（支援 SSE 串流模式）。

    OmniRoute 是 combo 路由伺服器，預設使用 SSE 串流回覆。
    此函數會：
      1. 發送 stream=true 的請求
      2. 分塊讀取 SSE 資料流，依換行符分割
      3. 合併所有 chunk 中的內容
      4. 組裝成 OpenAI 相容的非串流回應格式

    Args:
        messages: OpenAI 格式的 messages 列表
        temperature: 生成隨機性（0.0 ~ 1.0），越低越穩定
        max_tokens: 最大生成 token 數

    Returns:
        組裝後的 API 回應（OpenAI 非串流格式）

    Raises:
        requests.RequestException: API 呼叫失敗時拋出
    """
    url = f"{OMNIROUTE_BASE_URL}/chat/completions"

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,  # OmniRoute combo 路由需要串流模式
    }

    headers = {
        "Content-Type": "application/json",
    }

    logger.info(f"呼叫 OmniRoute (SSE): model={MODEL_NAME}, url={url}")

    # 發送串流請求
    response = requests.post(
        url, json=payload, headers=headers, timeout=180, stream=True
    )
    response.raise_for_status()

    # 解析 SSE 串流，合併所有 chunk
    full_content = ""
    finish_reason = None
    usage_data = None
    response_model = MODEL_NAME

    # 使用大塊讀取（4096 bytes）以避免 UTF-8 中文字被截斷損毀
    # 保留未完成行在緩衝區中，遇到換行時才處理
    buffer = ""
    for chunk in response.iter_content(chunk_size=4096):
        if chunk is None:
            continue

        # 將 bytes 解碼為字串
        decoded = chunk.decode("utf-8", errors="replace")
        buffer += decoded

        # 依換行符分割緩衝區
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            if not line:
                continue

            # SSE 註解行（以 : 開頭）直接跳過
            if line.startswith(":"):
                continue

            # 資料行必須以 "data: " 開頭
            if not line.startswith("data: "):
                continue

            data_str = line[6:]  # 去掉 "data: " 前綴
            if data_str.strip() == "[DONE]":
                break

            try:
                chunk_data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # 更新模型名稱
            chunk_model = chunk_data.get("model")
            if chunk_model:
                response_model = chunk_model

            # 累加 content delta
            # 【重要】OmniRoute 的不同模型會使用不同的欄位名稱：
            #   - OpenAI 標準: delta.content
            #   - DeepSeek/推理模型: delta.reasoning, delta.reasoning_content
            #   - Claude: delta.content (部分有 delta.reasoning)
            # 我們依序嘗試三種欄位，取第一個非空值
            choices = chunk_data.get("choices", [])
            for choice in choices:
                delta = choice.get("delta", {})
                content_text = (
                    delta.get("content")
                    or delta.get("reasoning")
                    or delta.get("reasoning_content")
                    or ""
                )
                if content_text:
                    full_content += content_text

                # 記錄 finish_reason
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason = fr

            # 記錄用量資訊
            usage = chunk_data.get("usage")
            if usage:
                usage_data = usage

        # 如果 buffer 中還有 [DONE]，處理它
        if "[DONE]" in buffer:
            break

    # 確保緩衝區中剩餘的資料也被處理
    if buffer.strip():
        line = buffer.strip()
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str.strip() != "[DONE]":
                try:
                    chunk_data = json.loads(data_str)
                    for choice in chunk_data.get("choices", []):
                        delta = choice.get("delta", {})
                        content_text = (
                            delta.get("content")
                            or delta.get("reasoning")
                            or delta.get("reasoning_content")
                            or ""
                        )
                        if content_text:
                            full_content += content_text
                except (json.JSONDecodeError, KeyError):
                    pass

    logger.info(f"OmniRoute 串流完成 (model={response_model}), 共 {len(full_content)} 字元")

    # 組裝成 OpenAI 非串流回應格式
    assembled = {
        "id": f"gen-{response_model}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response_model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_content,
                },
                "finish_reason": finish_reason or "stop",
            }
        ],
    }
    if usage_data:
        assembled["usage"] = usage_data

    return assembled


# ============================================================
# 解析 AI 回覆中的 JSON 內容
# ============================================================
def parse_ai_response(api_response: dict[str, Any]) -> dict[str, Any]:
    """
    從 OmniRoute API 的回應中提取並解析 JSON 內容。

    OpenAPI 相容的回應格式為：
      {
        "choices": [
          {
            "message": {
              "content": "{ ... JSON 字串 ... }"
            }
          }
        ]
      }

    此函數會嘗試：
      1. 直接使用 json.loads 解析
      2. 若失敗，嘗試使用 Regex 從回覆中擷取 JSON 區塊
      3. 若還是失敗，拋出 ValueError

    Args:
        api_response: OmniRoute API 的原始回應字典

    Returns:
        解析後的 Python 字典

    Raises:
        ValueError: 無法從回覆中解析出有效 JSON
    """
    try:
        content = api_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"無法從 API 回應中取得 content: {e}")

    # 嘗試 1：直接解析
    content_stripped = content.strip()
    if content_stripped.startswith("{"):
        try:
            return json.loads(content_stripped)
        except json.JSONDecodeError:
            pass

    # 嘗試 2：若回覆被 Markdown 程式碼區塊包裹（```json ... ```）
    json_match = re.search(
        r"```(?:json)?\s*\n?({.*?})\n?\s*```", content_stripped, re.DOTALL
    )
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 嘗試 3：找尋第一個 { 到最後一個 }
    first_brace = content_stripped.find("{")
    last_brace = content_stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(content_stripped[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    # 全部失敗
    raise ValueError(
        f"無法從 AI 回覆中解析 JSON。原始內容：{content_stripped[:200]}"
    )


# ============================================================
# 主要 AI 處理入口
# ============================================================
def process_with_ai(
    user_text: str,
    image_base64: Optional[str] = None,
    defense_mode: bool = False,
) -> dict[str, Any]:
    """
    整合 AI 處理流程的對外接口。

    流程：
      1. 根據模式（防禦/結算）建構系統提示詞
      2. 建構使用者訊息（含圖片或純文字）
      3. 呼叫 OmniRoute API
      4. 解析回傳的 JSON
      5. 【重要】傳回前會自動對 tags 進行清洗（移除詞性標記）

    Args:
        user_text: 使用者輸入的文字內容
        image_base64: 圖片的 Base64 編碼（可為 None）
        defense_mode: 是否為防禦模式（菜單破譯）

    Returns:
        包含分析結果的字典，例如：
        {
            "mode": "settlement",
            "dish_name": "招牌三寶便當",
            "calories": 850,
            "protein": 35,
            "fat": 40,
            "carbs": 80,
            "comment": "...",
            "tags": ["便當", "高熱量"]
        }
    """
    # Step 1: 建構系統提示詞
    system_prompt = build_system_prompt(defense_mode)

    # Step 2: 建構使用者訊息
    user_message_content = build_user_message(user_text, image_base64, defense_mode)

    # Step 3: 組合完整 messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message_content},
    ]

    # Step 4: 呼叫 OmniRoute API
    api_response = call_omniroute(messages)

    # Step 5: 從原始回應中提取文字，供後續使用
    raw_text = api_response.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Step 6: 嘗試解析 JSON，若失敗則建構降級回覆
    try:
        result = parse_ai_response(api_response)
    except ValueError:
        logger.warning("AI 回覆中不包含有效的 JSON，使用原始文字作為降級回覆")
        if defense_mode:
            result = {
                "mode": "defense",
                "original_menu": user_text[:100],
                "recommendation": "（暫時無法分析，請重新嘗試）",
                "reason": "AI 正在思考中，請稍後再試一次 😅",
                "comment": raw_text[:500] if raw_text else "模型暫時無法產出分析結果",
                "tags": ["請重試"],
            }
        else:
            result = {
                "mode": "settlement",
                "dish_name": "（暫時無法辨識）",
                "calories": 0,
                "protein": 0,
                "fat": 0,
                "carbs": 0,
                "comment": raw_text[:500] if raw_text else "模型暫時無法產出分析結果，請再試一次 😅",
                "tags": ["請重試"],
            }
        return result

    # Step 7: 驗證結果 — 檢查是否為模板佔位文字（模型未輸出實際內容）
    # 若 recommendation 或 dish_name 的內容看起來像 system prompt 模板，
    # 代表模型只輸出了推理文字而沒有產出最終內容
    if defense_mode:
        template_markers = ["你推薦的最佳低卡選擇", "原始選擇可節省"]
        rec = result.get("recommendation", "")
        if any(marker in rec for marker in template_markers):
            logger.warning("AI 傳回了模板內容（模型未產出實際分析），使用推理文字作為 comment")
            result["recommendation"] = "（暫時無法分析，請重新嘗試）"
            result["reason"] = "AI 正在思考中，請稍後再試一次 😅"
            # 嘗試從原始內容中提取一些文字作為 fallback
            raw_text = api_response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if raw_text:
                result["comment"] = raw_text[:500]
    else:
        template_markers = ["招牌三寶便當", "便當"]
        dish = result.get("dish_name", "")
        if any(marker in dish for marker in template_markers) and "三寶" not in user_text:
            logger.warning("AI 傳回了模板內容（模型未產出實際分析）")
            result["dish_name"] = "（暫時無法辨識，請重新嘗試）"
            result["comment"] = "AI 正在思考中，請稍後再試一次 😅"
            raw_text = api_response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if raw_text:
                result["comment"] = raw_text[:500]

    # Step 7: 清洗標籤（移除詞性標記）
    if "tags" in result and isinstance(result["tags"], list):
        result["tags"] = clean_tags(result["tags"])

    logger.info(f"AI 處理完成，模式={'防禦' if defense_mode else '結算'}")

    return result
