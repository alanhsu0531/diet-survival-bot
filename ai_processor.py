# ============================================================
# AI 減肥生存管家 — AI 處理核心 (ai_processor.py)
# ============================================================
#
# 本模組負責：
#   1. 呼叫 OpenRouter API（相容於 OpenAI API 格式）
#      也支援其他 OpenAI 相容 API（如 OmniRoute 本機開發用）
#   2. 提供兩種 AI 分析模式：
#      A. 防禦模式（菜單破譯）— 搭配照片與文字給出低卡建議
#      B. 結算模式（毒舌紀錄）— 辨識便當、估算營養、毒舌評語
#   3. 使用正規表達式清洗 AI 生成的中文標籤
#
# 預設使用 OpenRouter 免費 API，只需在環境變數中設定 API Key。
# 若本機有 OmniRoute，將 OMNIROUTE_BASE_URL 改回本機位址即可。
# ============================================================

import os
import re
import json
import logging
from typing import Any, Optional

from dotenv import load_dotenv
import requests

# 載入 .env 環境變數（本機開發用，Render 直接用環境變數）
load_dotenv()

# ---------- 日誌設定 ----------
logger = logging.getLogger(__name__)

# ---------- API 伺服器設定 ----------
# 預設使用 OpenRouter 免費 API（須設定 OPENROUTER_API_KEY）
# 若本地有 OmniRoute，可改為 http://localhost:20128/v1
OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "https://openrouter.ai/api/v1")

# OpenRouter 免費模型推薦：
#   google/gemma-4-31b-it:free        — Google Gemma 4 31B，品質好 ✅ 推薦
#   google/gemma-4-26b-a4b-it:free    — 較小更快
#   openrouter/free                   — 自動路由到最佳免費模型
#   nvidia/nemotron-3-super-120b-a12b:free — 超大模型
#
# 【注意】若你有 OpenAI/Anthropic API Key，也可改為：
#   gpt-4o-mini
#   claude-sonnet-4-20250514
MODEL_NAME = os.getenv("AI_MODEL", "openrouter/free")

# 圖片用視覺模型（支援多模態輸入的免費模型）
# nvidia/nemotron-nano-12b-v2-vl:free 支援 Vision-Language
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

# OpenRouter API Key（Render 環境變數中設定）
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


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
      模式：\\s*[（(][^)）]*[）)]\\s*
      - \\s*            ：匹配括號前後的空白
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
    pattern = re.compile(r"\s*[（(][^)）]*[）)]\s*")

    cleaned = []
    for tag in tags:
        cleaned_tag = pattern.sub("", tag)
        cleaned_tag = cleaned_tag.strip()
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
        return """你是一位毒舌且幽默的減肥教練，擅長從照片辨識任何食物與份量。
使用者會傳送任何餐點或食物的照片，有時會附帶文字說明。請分析每一樣你看見的食物。

【圖片分析步驟 — 必須先做完整的視覺描述再估算】
1. 仔細觀察照片中的每一個食物項目，列出你看見的所有食材
2. 判斷每項食物的烹調方式（炸、蒸、炒、烤、滷、生等）
3. 用視覺參考估算份量：
   - 一個拳頭 ≈ 1 碗飯 / 1 杯
   - 一個手掌（不含手指）≈ 3oz / 85g 肉類
   - 大拇指 ≈ 1 湯匙油脂
   - 一副撲克牌大小 ≈ 1 份肉排
4. 逐項估算每種食物的熱量與營養，最後加總
5. 最後用毒舌風格寫評語

請務必以以下的 JSON 格式回覆（只能回傳 JSON，不要加 Markdown 程式碼區塊、不要表格、不要列表）：

{
    "mode": "settlement",
    "dish_name": "辨識出的餐點或食物名稱，例如：煎蛋、牛肉麵、水果沙拉",
    "calories": 250,
    "protein": 12,
    "fat": 18,
    "carbs": 2,
    "meal_type": "早餐",
    "cooking_methods": ["煎"],
    "ingredients": "雞蛋、食用油",
    "comment": "毒舌或鼓勵的評語（30~80字，語氣幽默，不可以有 ** 或 ## 等記號，純文字）",
    "tags": ["早餐", "高蛋白"]
}

注意事項：
- 任何食物都可以分析，不限便當！一顆蘋果、一碗麵、一杯飲料都可以
- 熱量與三大營養素請盡量合理估算，單位分別為大卡與公克 (g)
- calories/protein/fat/carbs 請填數字（非字串），無法判斷就估算，不要填 0
- meal_type 請依用餐時間填入：早餐/午餐/晚餐/點心
- cooking_methods 請列出 1~3 種烹調方式
- ingredients 請用頓號分隔，列出照片中可見的所有食材
- comment 請純文字，不可包含任何 Markdown 語法（**、##、| 等）
- 標籤 (tags) 請給出 2~4 個中文關鍵字
- 標籤中【不要附加詞性標記】"""


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
    if defense_mode:
        text_prefix = "請幫我分析這份菜單，給我低卡建議：\n\n"
    else:
        text_prefix = "請幫我結算這個便當的營養與熱量：\n\n"

    content: list[dict[str, Any]] = []

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
# 呼叫 API 伺服器（OpenAI 相容格式）
# ============================================================
def call_omniroute(
    messages: list[dict[str, Any]],
    temperature: float = 0.3,
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    向 API 伺服器（OpenRouter / OmniRoute）發送聊天完成請求。

    使用標準 OpenAI 相容的 /chat/completions 端點，非串流模式。

    Args:
        messages: OpenAI 格式的 messages 列表
        temperature: 生成隨機性（0.0 ~ 1.0），越低越穩定
        max_tokens: 最大生成 token 數

    Returns:
        API 回傳的完整 JSON 回應（dict 格式）

    Raises:
        requests.RequestException: API 呼叫失敗時拋出
    """
    url = f"{OMNIROUTE_BASE_URL}/chat/completions"

    effective_model = model or MODEL_NAME
    payload = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
    }

    # ---------- OpenRouter 專用 Headers ----------
    # 只有在 OMNIROUTE_BASE_URL 指向 OpenRouter 時才需要
    if "openrouter.ai" in OMNIROUTE_BASE_URL.lower():
        if not OPENROUTER_API_KEY:
            logger.warning(
                "OPENROUTER_API_KEY 未設定！請在 Render 環境變數中新增。"
            )
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
        # OpenRouter 建議提供的辨識資訊（僅限 ASCII）
        headers["HTTP-Referer"] = "https://github.com/alanhsu0531/diet-survival-bot"
        headers["X-Title"] = "AI Diet Survival Bot"

    logger.info(f"呼叫 API: model={MODEL_NAME}, url={url}")

    response = requests.post(
        url, json=payload, headers=headers, timeout=60
    )

    # 若 API 回傳錯誤，記錄詳細資訊
    if response.status_code != 200:
        logger.error(
            f"API 錯誤 (status={response.status_code}): {response.text[:300]}"
        )
    response.raise_for_status()

    result = response.json()
    logger.debug(f"API 回應摘要: {json.dumps(result, ensure_ascii=False)[:200]}...")

    return result


# ============================================================
# 解析 AI 回覆中的 JSON 內容
# ============================================================
def parse_ai_response(api_response: dict[str, Any]) -> dict[str, Any]:
    """
    從 API 的回應中提取並解析 JSON 內容。

    OpenAI 相容的回應格式為：
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
        api_response: API 的原始回應字典

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
# 圖片專用 AI 處理入口（使用視覺模型）
# ============================================================
def process_with_ai_image(
    user_text: str,
    image_base64: str,
    defense_mode: bool = False,
) -> dict[str, Any]:
    """
    給圖片專用的 AI 處理，使用 VISION_MODEL 確保模型支援圖片辨識。
    若圖片模型失敗，會自動降級為一般模型重試一次。
    """
    # 先用視覺模型嘗試
    try:
        return process_with_ai(
            user_text=user_text,
            image_base64=image_base64,
            defense_mode=defense_mode,
            model_override=VISION_MODEL,
        )
    except Exception as e:
        logger.warning(f"視覺模型 ({VISION_MODEL}) 失敗: {e}，降級為一般模型")
        # 降級為一般 model 再試一次
        return process_with_ai(
            user_text=user_text,
            image_base64=image_base64,
            defense_mode=defense_mode,
            model_override=None,
        )


# ============================================================
# 主要 AI 處理入口
# ============================================================
def process_with_ai(
    user_text: str,
    image_base64: Optional[str] = None,
    defense_mode: bool = False,
    model_override: Optional[str] = None,
) -> dict[str, Any]:
    """
    整合 AI 處理流程的對外接口。

    流程：
      1. 根據模式（防禦/結算）建構系統提示詞
      2. 建構使用者訊息（含圖片或純文字）
      3. 呼叫 API
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

    # Step 4: 呼叫 API
    api_response = call_omniroute(messages, model=model_override)

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

    # Step 7: 清洗標籤（移除詞性標記）
    if "tags" in result and isinstance(result["tags"], list):
        result["tags"] = clean_tags(result["tags"])

    logger.info(f"AI 處理完成，模式={'防禦' if defense_mode else '結算'}")

    return result
