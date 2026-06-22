from flask import Flask, request
import requests
import os
import re
from datetime import datetime

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


# =====================
# 健康檢查
# =====================
@app.route("/")
def home():
    return "OK"


# =====================
# 地址清理
# =====================
def clean_address(addr):
    if not addr:
        return ""

    addr = addr.strip()

    for city in ["台北市", "臺北市", "北市", "新北市", "桃園市"]:
        if addr.startswith(city):
            return addr.replace(city, "", 1).strip()

    return addr


# =====================
# 日期（今天不顯示）
# =====================
def format_date(text):
    if not text:
        return ""

    today = datetime.now()

    nums = re.findall(r"\d+", text)

    if len(nums) >= 2:
        m, d = int(nums[0]), int(nums[1])

        if m == today.month and d == today.day:
            return ""

        return f"{m}/{d}"

    return ""


# =====================
# 🚀 時間（穩定版，防 00:00）
# =====================
def format_time(text):
    if not text:
        return ""

    text = text.strip()
    text = text.replace("預約", "").replace("時間", "")
    text = text.replace("：", "").replace(":", "")

    # 上午 / 下午 + 時間
    m = re.search(r"(上午|下午)?\s*\d{1,2}\s*[：:]?\s*\d{0,2}", text)
    if m:
        t = m.group()
        t = t.replace(" ", "").replace("點", ":").replace("：", ":")

        # 如果只有小時
        if ":" not in t:
            t = f"{t}:00"

        # 防呆：避免 00:00
        if t == "00:00":
            return ""

        return t

    # 只有數字
    m = re.search(r"\d{1,2}", text)
    if m:
        num = m.group()

        if num in ["0", "00"]:
            return ""

        return f"{num}:00"

    return ""


# =====================
# 主解析
# =====================
def parse_message(text):

    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""
    date = ""
    time = ""

    for line in text.split("\n"):

        line = line.strip()
        if not line:
            continue

        line = line.replace(":", "：")

        # 日期
        if "日期" in line:
            date = format_date(line.split("：")[-1])

        # 時間
        if "時間" in line:
            time = format_time(line.split("：")[-1])

        # 上車
        if "上車" in line and not pickup:
            pickup = line.split("：")[-1].strip()

        # 下車
        if "下車" in line and not dropoff:
            dropoff = line.split("：")[-1].strip()

        # 人數
        if "人數" in line:
            nums = re.findall(r"\d+", line)
            if nums:
                pax = int(nums[0])

        # 備註
        if "備註" in line:
            remark = line.split("：")[-1].strip()

    # 沒上車地址直接不回
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
    output = []

    # 日期 + 時間（只顯示有的）
    dt = " ".join([x for x in [date, time] if x])
    if dt:
        output.append(dt)

    # 上車
    output.append(f"⬆️{clean_address(pickup)}")

    # 下車（有才顯示）
    if dropoff:
        output.append(f"下車地址：{clean_address(dropoff)}")

    # 底部資訊（人數 >4 + 備註）
    bottom = []

    if pax > 4:
        text = f"({pax})"
        if fee > 0:
            text += f"➕{fee}"
        bottom.append(text)

    if remark:
        bottom.append(f"✅{remark}")

    if bottom:
        output.append("".join(bottom))

    return "\n".join(output)


# =====================
# LINE webhook
# =====================
@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_json()

    if not body:
        return "OK", 200

    for event in body.get("events", []):

        if event.get("type") != "message":
            continue

        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue

        text = msg.get("text", "")
        reply_token = event.get("replyToken")

        result = parse_message(text)

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