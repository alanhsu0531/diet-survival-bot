import os, requests
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
auth = {"Authorization": f"Bearer {token}"}

# 1. 看目前有哪些 Rich Menu
r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=auth)
menus = r.json().get("richmenus", [])
print(f"Rich Menus 數量: {len(menus)}")

for rm in menus:
    rid = rm["richMenuId"]
    # 2. 檢查每一張圖片有沒有上傳成功
    img_r = requests.get(f"https://api-data.line.me/v2/bot/richmenu/{rid}/content", headers=auth)
    print(f"  {rm['name']}: {rid}")
    print(f"    圖片: {'✅' if img_r.status_code == 200 else '❌'} ({img_r.status_code})")
    print(f"    圖片大小: {len(img_r.content)} bytes" if img_r.status_code == 200 else "")

    # 3. 強制設為預設（用正確的 API）
    set_r = requests.post(f"https://api.line.me/v2/bot/user/all/richmenu/{rid}", headers=auth)
    print(f"    設預設: {set_r.status_code}")

# 4. 確認預設狀態
r2 = requests.get("https://api.line.me/v2/bot/richmenu/default", headers=auth)
print(f"\n目前預設: {r2.status_code}")
if r2.status_code == 200:
    print(f"  預設ID: {r2.json().get('richMenuId')}")
