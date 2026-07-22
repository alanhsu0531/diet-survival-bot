import os, requests
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=h)
menus = r.json().get("richmenus", [])
print(f"找到 {len(menus)} 個 Rich Menu:")

if not menus:
    print("沒有 Rich Menu，請先執行 python3 setup_rich_menu.py")
    exit()

rid = menus[-1]["richMenuId"]
print(f"最新: {rid}")

# 方法1: 標準 API
r1 = requests.post(f"https://api.line.me/v2/bot/richmenu/{rid}/default", headers=h)
print(f"方法1 (richmenu/ID/default): {r1.status_code} - {r1.text[:100]}")

# 方法2: user/all API
r2 = requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{rid}", headers=h)
print(f"方法2 (user/all/richmenu/ID): {r2.status_code} - {r2.text[:100]}")
