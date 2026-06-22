from flask import Flask, request
import requests
import os

app = Flask(__name__)

# LINE Channel Access Token
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


# =====================
# 地址簡化
# =====================
def clean(addr):
    if not addr:
        return ""

    for city in ["台北市", "新北市", "桃園市"]:
        if addr.startswith(city):
            return addr.replace(city, "", 1)

    return addr


# =====================
# 訂單解析
# =====================
def parse_order(text):
    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""

    for line in text.split("\n"):

        line = line.replace(":", "：")

        if "上車地址" in line:
            pickup = line.split("：", 1)[1].strip()

        elif "下車地址" in line:
            dropoff = line.split("：", 1)[1].strip()

        elif "乘坐人數" in line:
            try:
                pax = int(line.split("：", 1)[1].strip())
            except:
                pax = 1

        elif "其他備註" in line:
            remark = line.split("：", 1)[1].strip()

    # 沒有上車地址就不回覆
    if not pickup:
        return ""

    # =====================
    # 加價規則
    # =====================
    fee = 0

    if pax == 5:
        fee = 100

    elif pax == 6:
        fee = 200

    # =====================
    # 組輸出
    # =====================
    result = f"⬆️{clean(pickup)}"

    # 有下車地址才顯示
    if dropoff:
        result += f"\n下車地址：{clean(dropoff)}"

    # 最後一行
    extra = ""

    # 人數大於4才顯示
    if pax > 4:
        extra += f"({pax})"

        if fee > 0:
            extra += f"➕{fee}"

    # 備註
    if remark:
        extra += f"✅{remark}"

    if extra:
        result += f"\n{extra}"

    return result


# =====================
# 首頁
# =====================
@app.route("/")
def home():
    return "OK"


# =====================
# LINE Webhook
# =====================
@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    print(body)

    for event in body.get("events", []):

        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text = message.get("text", "")
        reply_token = event.get("replyToken")

        result = parse_order(text)

        if not result:
            continue

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

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)