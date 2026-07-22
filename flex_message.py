# ============================================================
# AI 減肥生存管家 — Line Flex Message 卡片回覆 (flex_message.py)
# ============================================================
# 將 AI 分析結果轉換為 Line Flex Message 格式，讓回覆更美觀。
#
# Flex Message 參考文件：
#   https://developers.line.biz/en/docs/messaging-api/flex-message-layout/
# ============================================================

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_flex_message(data: dict[str, Any], defense_mode: bool) -> dict[str, Any]:
    """
    根據 AI 分析結果建構 Flex Message 卡片。

    回傳值為 dict，可直接作為 ReplyMessageRequest 的 messages 內容。

    Args:
        data: AI 分析結果字典
        defense_mode: 是否為防禦模式

    Returns:
        Flex Message 字典（line-bot-sdk 可接受的格式）
    """
    if defense_mode:
        return _build_defense_flex(data)
    return _build_settlement_flex(data)


# ============================================================
# 顏色設定
# ============================================================
COLOR_PRIMARY = "#4A90D9"      # 主要藍色
COLOR_WARNING = "#E8913A"      # 警告橘色
COLOR_DANGER = "#D9534F"       # 危險紅色
COLOR_SUCCESS = "#5CB85C"      # 綠色（低卡/健康）
COLOR_BG = "#FFFFFF"           # 背景白色
COLOR_TEXT = "#333333"         # 主要文字深灰
COLOR_SUBTEXT = "#888888"      # 次要文字淺灰
COLOR_BORDER = "#F0F0F0"      # 邊框淺灰


# ============================================================
# 字型大小輔助函數
# ============================================================
def _text(text: str, size: str = "md", weight: str = "regular",
           color: str = COLOR_TEXT, wrap: bool = True, align: str = "start",
           flex: int = 0, margin: str = None) -> dict:
    """建立 Flex Text 元件"""
    item: dict = {
        "type": "text",
        "text": text,
        "size": size,
        "weight": weight,
        "color": color,
        "wrap": wrap,
    }
    if align != "start":
        item["align"] = align
    if flex:
        item["flex"] = flex
    if margin:
        item["margin"] = margin
    return item


def _separator(margin: str = "md") -> dict:
    """建立分隔線"""
    return {"type": "separator", "margin": margin, "color": COLOR_BORDER}


def _spacer(size: str = "sm") -> dict:
    """建立空白間距"""
    return {"type": "spacer", "size": size}


def _box(layout: str, contents: list, margin: str = "none",
         padding: str = "none") -> dict:
    """建立 Box 容器"""
    return {
        "type": "box",
        "layout": layout,
        "contents": contents,
        "margin": margin,
        "paddingAll": padding,
    }


def _nutrient_row(icon: str, label: str, value: Any, unit: str,
                  color: str = COLOR_TEXT) -> dict:
    """建立營養素橫列（圖示 + 名稱 + 數值）"""
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            _text(f"{icon} {label}", size="sm", color=COLOR_SUBTEXT, flex=1),
            _text(f"{value} {unit}", size="sm", weight="bold",
                  color=color, flex=0),
        ],
        "spacing": "sm",
    }


def _calorie_color(cal: float) -> str:
    """根據熱量高低回傳顏色"""
    if cal < 400:
        return COLOR_SUCCESS
    elif cal < 700:
        return COLOR_WARNING
    return COLOR_DANGER


# ============================================================
# 結算模式 Flex Message
# ============================================================
def _build_settlement_flex(data: dict) -> dict:
    """結算模式的卡片佈局"""
    dish_name = data.get("dish_name", "未知餐點")
    calories = data.get("calories", 0)
    protein = data.get("protein", 0)
    fat = data.get("fat", 0)
    carbs = data.get("carbs", 0)
    comment = data.get("comment", "")
    tags = data.get("tags", [])

    cal_color = _calorie_color(calories)

    # 卡片內容組裝
    contents: list[dict] = [
        # 標題區
        _text("🍽️ 結算模式", size="xs", color=COLOR_SUBTEXT),
        _text(dish_name, size="xl", weight="bold", color=COLOR_TEXT),
        _separator("md"),

        # 熱量（大號顯示）
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                _text("🔥 熱量", size="md", color=COLOR_SUBTEXT, flex=1),
                _text(f"{calories}", size="xxl", weight="bold",
                      color=cal_color, flex=0),
                _text("大卡", size="sm", color=COLOR_SUBTEXT, flex=0,
                      align="end"),
            ],
            "margin": "md",
        },

        _spacer("sm"),

        # 三大營養素
        _box("horizontal", [
            {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    _text("🥩 蛋白質", size="xs", color=COLOR_SUBTEXT),
                    _text(f"{protein}g", size="lg", weight="bold",
                          color=COLOR_PRIMARY),
                ],
                "flex": 1,
            },
            {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    _text("🧈 脂肪", size="xs", color=COLOR_SUBTEXT),
                    _text(f"{fat}g", size="lg", weight="bold",
                          color=COLOR_WARNING),
                ],
                "flex": 1,
            },
            {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    _text("🍚 碳水", size="xs", color=COLOR_SUBTEXT),
                    _text(f"{carbs}g", size="lg", weight="bold",
                          color=COLOR_PRIMARY),
                ],
                "flex": 1,
            },
        ], margin="md"),

        _separator("md"),
    ]

    # 毒舌評語
    if comment:
        comment_short = comment if len(comment) <= 100 else comment[:97] + "..."
        contents.append(
            _box("horizontal", [
                _text("💬", size="sm", flex=0),
                _text(comment_short, size="sm", color=COLOR_TEXT, flex=1),
            ], margin="md")
        )

    # 標籤
    if tags:
        tag_text = "  ".join([f"#{t}" for t in tags])
        contents.extend([
            _separator("md"),
            _text(tag_text, size="xs", color=COLOR_SUBTEXT, margin="md"),
        ])

    return {
        "type": "flex",
        "altText": f"🍽️ {dish_name} — {calories} 大卡",
        "contents": {
            "type": "bubble",
            "styles": {
                "header": {"backgroundColor": COLOR_PRIMARY},
                "body": {"separator": True},
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents,
                "spacing": "sm",
            },
        },
    }


# ============================================================
# 防禦模式 Flex Message
# ============================================================
def _build_defense_flex(data: dict) -> dict:
    """防禦模式的卡片佈局"""
    original = data.get("original_menu", "")
    recommendation = data.get("recommendation", "（暫無建議）")
    reason = data.get("reason", "")
    calories_saved = data.get("calories_saved", 0)
    tags = data.get("tags", [])

    contents: list[dict] = [
        _text("🥗 防禦模式", size="xs", color=COLOR_SUBTEXT),
        _text("菜單破譯報告", size="xl", weight="bold", color=COLOR_TEXT),
        _separator("md"),
    ]

    if original:
        contents.append(
            _box("horizontal", [
                _text("📋 原始菜單", size="sm", color=COLOR_SUBTEXT, flex=1),
            ], margin="md")
        )
        short_menu = original if len(original) <= 60 else original[:57] + "..."
        contents.append(
            _text(short_menu, size="sm", color=COLOR_TEXT, margin="sm")
        )

    # 推薦選擇（重點顯示）
    contents.extend([
        _separator("md"),
        _box("horizontal", [
            _text("✅ 推薦選擇", size="sm", color=COLOR_SUCCESS, flex=1),
        ], margin="md"),
        _text(recommendation, size="md", weight="bold", color=COLOR_TEXT,
              margin="sm"),
    ])

    if reason:
        contents.extend([
            _spacer("sm"),
            _text(f"💡 {reason}", size="sm", color=COLOR_SUBTEXT),
        ])

    if calories_saved:
        contents.extend([
            _separator("md"),
            _box("horizontal", [
                _text("🔥 節省", size="sm", color=COLOR_SUBTEXT, flex=1),
                _text(f"{calories_saved} 大卡", size="lg", weight="bold",
                      color=COLOR_SUCCESS, flex=0),
            ], margin="md"),
        ])

    if tags:
        tag_text = "  ".join([f"#{t}" for t in tags])
        contents.extend([
            _separator("md"),
            _text(tag_text, size="xs", color=COLOR_SUBTEXT, margin="md"),
        ])

    return {
        "type": "flex",
        "altText": f"🥗 {recommendation[:40]}",
        "contents": {
            "type": "bubble",
            "styles": {
                "header": {"backgroundColor": COLOR_SUCCESS},
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents,
                "spacing": "sm",
            },
        },
    }
