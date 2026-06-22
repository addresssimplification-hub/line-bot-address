from flask import Flask, request
import requests
import os
import re

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
            addr = addr.replace(city, "", 1).strip()

    return addr


# =====================
# 日期處理
# =====================
def parse_date(text):
    if not text:
        return ""

    text = text.strip()

    if "當日" in text:
        return ""

    nums = re.findall(r"\d+", text)

    if len(nums) >= 2:
        return f"{int(nums[0])}/{int(nums[1])}"

    return ""


# =====================
# 🔥 時間處理（完整版：凌晨/早上/下午/晚上）
# =====================
def parse_time(text):
    if not text:
        return ""

    text = text.strip()
    text = text.replace("預約", "").replace("時間", "").replace("：", "").replace(" ", "")

    if not text:
        return ""

    # =====================
    # 語意時間
    # =====================
    period = ""

    if "凌晨" in text:
        period = "凌晨"
    elif "早上" in text:
        period = "早上"
    elif "上午" in text:
        period = "上午"
    elif "中午" in text:
        period = "中午"
    elif "下午" in text:
        period = "下午"
    elif "傍晚" in text:
        period = "傍晚"
    elif "晚上" in text:
        period = "晚上"

    # =====================
    # 數字時間
    # =====================
    match = re.search(r"(\d{1,2})(?:[:：]?(\d{0,2}))?", text)

    if not match:
        return period if period else ""

    hour = match.group(1)
    minute = match.group(2)

    if not hour or hour == "0":
        return period

    if not minute:
        minute = "00"

    if len(minute) == 1:
        minute += "0"

    if period:
        return f"{period}{int(hour)}:{minute}"

    return f"{int(hour)}:{minute}"


# =====================
# 解析訊息
# =====================
def parse_message(text):

    pickup = ""
    dropoff = ""
    pax = 0
    remark = ""
    date = ""
    time = ""

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "上車地址" in line:
            pickup = line.split("：")[-1].strip()

        elif "下車地址" in line:
            dropoff = line.split("：")[-1].strip()

        elif "乘坐人數" in line:
            nums = re.findall(r"\d+", line)
            pax = int(nums[0]) if nums else 0

        elif "其他備註" in line:
            remark = line.split("：")[-1].strip()

        elif "日期" in line:
            date = parse_date(line.split("：")[-1])

        elif "時間" in line:
            time = parse_time(line.split("：")[-1])

    # 沒上車直接不回
    if not pickup:
        return ""

    output = []

    # 日期 + 時間
    dt = " ".join([x for x in [date, time] if x])
    if dt:
        output.append(dt)

    # 上車
    output.append(f"⬆️{clean_address(pickup)}")

    # 下車（可選）
    if dropoff:
        output.append(f"下車地址：{clean_address(dropoff)}")

    # 最下方資訊（人數 + 備註）
    bottom = []

    if pax > 4:
        bottom.append(f"({pax})")

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