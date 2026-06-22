from flask import Flask, request
import os
import requests

app = Flask(__name__)

# =====================
# LINE TOKEN（Render 環境變數）
# =====================
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
# 解析訊息
# =====================
def parse(text):
    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""

    for line in text.split("\n"):
        line = line.replace(":", "：")

        if "上車地址" in line:
            pickup = line.split("：")[-1].strip()

        elif "下車地址" in line:
            dropoff = line.split("：")[-1].strip()

        elif "乘坐人數" in line:
            try:
                pax = int(line.split("：")[-1].strip())
            except:
                pax = 1

        elif "其他備註" in line:
            remark = line.split("：")[-1].strip()

    fee = (pax - 4) * 100 if pax > 4 else 0

    result = f"⬆️{clean(pickup)}\n下車地址：{clean(dropoff)}\n({pax})"

    if fee > 0:
        result += f"➕{fee}"

    if remark:
        result += f"✅{remark}"

    return result


# =====================
# LINE webhook（REST API）
# =====================
@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    for event in body["events"]:

        # 只處理文字訊息
        if event["type"] != "message":
            continue

        if event["message"]["type"] != "text":
            continue

        text = event["message"]["text"]
        reply_token = event["replyToken"]

        msg = parse(text)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": msg
                }
            ]
        }

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

    return "OK", 200


# =====================
# 本地測試
# =====================
if __name__ == "__main__":
    app.run()
