import os, requests, io, time
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 刪除全部
r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=h)
for rm in r.json().get("richmenus", []):
    requests.delete(f'https://api.line.me/v2/bot/richmenu/{rm["richMenuId"]}', headers=h)
print("✅ 舊選單已清除")

# 4 格選單（2x2）
menu = {
    "size": {"width": 2500, "height": 843},
    "selected": True,
    "name": "diet-menu",
    "chatBarText": "功能選單",
    "areas": [
        {"bounds": {"x": 0, "y": 0, "width": 1250, "height": 421},
         "action": {"type": "cameraRoll", "label": "拍照分析"}},
        {"bounds": {"x": 1250, "y": 0, "width": 1250, "height": 421},
         "action": {"type": "message", "text": "防禦", "label": "防禦模式"}},
        {"bounds": {"x": 0, "y": 421, "width": 1250, "height": 422},
         "action": {"type": "message", "text": "喝水", "label": "飲水紀錄"}},
        {"bounds": {"x": 1250, "y": 421, "width": 1250, "height": 422},
         "action": {"type": "message", "text": "記錄", "label": "記錄查詢"}},
    ]
}
r = requests.post("https://api.line.me/v2/bot/richmenu", headers=h, json=menu)
rid = r.json()["richMenuId"]
print("✅ 建立成功")

# 設計圖片
img = Image.new("RGB", (2500, 843), "#0f0f23")
draw = ImageDraw.Draw(img)

# 字型
font_icon = font_title = font_sub = None
for fp in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]:
    if os.path.exists(fp):
        font_icon = ImageFont.truetype(fp, 80)
        font_title = ImageFont.truetype(fp, 42)
        font_sub = ImageFont.truetype(fp, 26)
        break
if not font_icon:
    font_icon = font_title = font_sub = ImageFont.load_default()

W, H = 2500, 843
r2 = 28

# 4 格定義：(x1, y1, x2, y2, color, icon, title, sub)
cells = [
    (15, 10, 1242, 415, "#2ec4b6", "📸", "拍照分析", "拍食物自動算營養"),
    (1258, 10, 2485, 415, "#ff6b6b", "🥗", "防禦模式", "輸入菜單推薦低卡"),
    (15, 428, 1242, 833, "#4a90d9", "💧", "飲水紀錄", "記錄喝水提醒補水"),
    (1258, 428, 2485, 833, "#6c63ff", "📊", "記錄查詢", "查看飲食歷史紀錄"),
]

for x1, y1, x2, y2, color, icon, title, sub in cells:
    draw.rounded_rectangle([x1, y1, x2, y2], radius=r2, fill=color)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    # icon 白色圓底
    draw.ellipse([cx - 38, cy - 75, cx + 38, cy + 1], fill="white", width=0)
    draw.text((cx - 28, cy - 70), icon, fill=color, font=font_icon)

    # 標題
    b = draw.textbbox((0, 0), title, font=font_title)
    draw.text((cx - (b[2]-b[0])//2, cy + 20), title, fill="white", font=font_title)

    # 副標題
    b2 = draw.textbbox((0, 0), sub, font=font_sub)
    draw.text((cx - (b2[2]-b2[0])//2, cy + 70), sub, fill=(255,255,255,200), font=font_sub)

buf = io.BytesIO()
img.save(buf, format="PNG")

img_h = {"Authorization": f"Bearer {token}", "Content-Type": "image/png"}
requests.post(f"https://api-data.line.me/v2/bot/richmenu/{rid}/content", headers=img_h, data=buf.getvalue())
print("✅ 圖片上傳成功")

time.sleep(1)
requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{rid}", headers=h)
print("✅ 設為預設")

print("🎉 完成！重開 Line App 看看 4 格選單")
