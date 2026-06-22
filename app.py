from flask import Flask, request
import requests
import os
import re
from datetime import datetime

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
# 日期判斷（今天不顯示）
# =====================
def format_date(date_str):
    if not date_str:
        return ""

    today = datetime.now()

    try:
        # 6/29 or 06/29
        match = re.findall(r"\d+", date_str)
        if len(match) >= 2:
            m, d = int(match[0]), int(match[1])

            if m == today.month and d == today.day:
                return ""
            return f"{m}/{d}"
    except:
        pass

    return date_str


# =====================
# 時間處理
# =====================
def format_time(time_str):
    if not time_str:
        return ""

    time_str = time_str.strip()

    time_str = time_str.replace("預約", "")
    time_str = time_str.replace("：", "").strip()

    return time_str


# =====================
# 主解析
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
                date = format_date(parts[1].strip())

        # =====================
        # 時間
        # =====================
        if "時間" in normalized:
            parts = normalized.split("：", 1)
            if len(parts) > 1:
                time = format_time(parts[1])

        # =====================
        # 上車
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
        # 下車
        =====================
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

    # 沒上車不回覆
    if not pickup:
        return ""

    # =====================
    # 加價
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

    # 日期 + 時間
    dt = " ".join([x for x in [date, time] if x])

    if dt:
        result += dt + "\n"

    result += f"⬆️{clean(pickup)}"

    if dropoff:
        result += f"\n下車地址：{clean(dropoff)}"

    extra = ""

    if pax > 4:
        extra += f"({pax})"
        if fee > 0:
            extra += f"➕{fee}"

    if remark:
        extra += f"✅{remark}"

    if extra:
        result += f"\n{extra}"

    return result


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