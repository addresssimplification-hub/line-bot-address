from flask import Flask, request
import requests
import os

app = Flask(**name**)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# =====================

# 地址簡化

# =====================

def clean(addr):
if not addr:
return ""

```
for city in ["台北市", "新北市", "桃園市"]:
    if addr.startswith(city):
        return addr.replace(city, "", 1)

return addr
```

# =====================

# 訂單解析

# =====================

def parse_order(text):
pickup = ""
dropoff = ""
pax = 1
remark = ""

```
for line in text.split("\n"):

    line = line.replace(":", "：")

    if line.startswith("上車地址"):
        pickup = line.split("：", 1)[1].strip()

    elif line.startswith("下車地址"):
        dropoff = line.split("：", 1)[1].strip()

    elif line.startswith("乘坐人數"):
        try:
            pax = int(line.split("：", 1)[1].strip())
        except:
            pax = 1

    elif line.startswith("其他備註"):
        remark = line.split("：", 1)[1].strip()

fee = 0

if pax == 5:
    fee = 100
elif pax == 6:
    fee = 200

result = f"⬆️{clean(pickup)}\n下車地址：{clean(dropoff)}\n({pax})"

if fee > 0:
    result += f"➕{fee}"

if remark:
    result += f"✅{remark}"

return result
```

@app.route("/")
def home():
return "OK"

@app.route("/callback", methods=["POST"])
def callback():
body = request.get_json()

```
print("BODY =", body)

for event in body.get("events", []):

    if event.get("type") != "message":
        continue

    message = event.get("message", {})

    if message.get("type") != "text":
        continue

    text = message.get("text", "")

    reply_token = event.get("replyToken")

    result = parse_order(text)

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": result
            }
        ]
    }

    r = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=data
    )

    print("LINE API:", r.status_code, r.text)

return "OK", 200
```

if **name** == "**main**":
app.run()
