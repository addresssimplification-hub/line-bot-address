from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


# =====================
# 地址簡化
# =====================
def clean(addr):
    if not addr:
        return ""

    addr = addr.strip()

    city_list = [
        "台北市",
        "臺北市",
        "北市",
        "新北市",
        "桃園市"
    ]

    for city in city_list:
        if addr.startswith(city):
            return addr.replace(city, "", 1).strip()

    return addr


# =====================
# 訂單解析
# =====================
def parse_order(text):

    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""
    date = ""
    time = ""

    pickup_keywords = ["上車地址", "上車", "起點", "搭車", "接送"]
    dropoff_keywords = ["下車地址", "下車", "終點", "目的地", "送達"]
    remark_keywords = ["其他備註", "備註"]

    for line in text.split("\n"):

        line = line.strip()
        if not line:
            continue

        normalized = line.replace(":", "：")

        # =====================
        # 日期
        # =====================
        if "日期" in normalized:
            parts = normalized.split("：", 1)
            if len(parts) > 1:
                date = parts[1].strip()

        # =====================
        # 時間
        # =====================
        if "時間" in normalized:
            parts = normalized.split("：", 1)
            if len(parts) > 1:
                time = parts[1].strip().replace("預約", "").strip()

        # =====================
        # 上車地址
        # =====================
        if not pickup:
            for key in pickup_keywords:
                if key in normalized:

                    if "：" in normalized:
                        pickup = normalized.split("：", 1)[1].strip()
                    else:
                        pickup = normalized.replace(key, "").strip()

                    break

        # =====================
        # 下車地址
        # =====================
        if not dropoff:
            for key in dropoff_keywords:
                if key in normalized:

                    if "：" in normalized:
                        dropoff = normalized.split("：", 1)[1].strip()
                    else:
                        dropoff = normalized.replace(key, "").strip()

                    break

        # =====================
        # 人數
        =====================
        if any(k in normalized for k in ["乘坐人數", "搭乘人數", "人數"]):
            numbers = re.findall(r"\d+", normalized)
            if numbers:
                pax = int(numbers[0])

        # =====================
        # 備註
        =====================
        for key in remark_keywords:
            if key in normalized:

                if "：" in normalized:
                    remark = normalized.split("：", 1)[1].strip()

                break

    # 沒上車地址不回覆
    if not pickup:
        return ""

    # =====================
    # 加價規則
    =====================
    fee = 0
    if pax == 5:
        fee = 100
    elif pax == 6:
        fee = 200

    # =====================
    # 組輸出
    =====================
    result = ""

    # 日期時間
    if date or time:
        result += f"{date} {time}".strip() + "\n"

    result += f"⬆️{clean(pickup)}"

    if dropoff:
        result += f"\n下車地址：{clean(dropoff)}"

    extra = ""

    # 人數 >4 才顯示
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

    print("收到:", body)

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