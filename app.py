from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


# =====================
# 基本服務
# =====================
@app.route("/")
def home():
    return "OK"


# =====================
# 清理地址（避免「地址地址」問題）
# =====================
def clean_address(text):
    if not text:
        return ""

    text = text.strip()

    # 移除標籤
    for k in ["上車", "下車", "地址", "⬆️", "⬇️", "：", ":"]:
        text = text.replace(k, "")

    # 移除縣市前綴
    for city in ["台北市", "臺北市", "北市", "新北市", "桃園市"]:
        if text.startswith(city):
            text = text.replace(city, "", 1)

    return text.strip()


# =====================
# 智慧抓上下車
# =====================
def smart_parse(lines):
    pickup = ""
    dropoff = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "上車" in line or "⬆️" in line:
            pickup = clean_address(line)

        elif "下車" in line or "⬇️" in line:
            dropoff = clean_address(line)

    return pickup, dropoff


# =====================
# 日期處理
# =====================
def parse_date(text):
    if not text:
        return ""

    if "當日" in text:
        return ""

    nums = re.findall(r"\d+", text)

    if len(nums) >= 2:
        return f"{int(nums[0])}/{int(nums[1])}"

    return ""


# =====================
# 時間處理（1545 / 下午5:00 / 晚上）
# =====================
def parse_time(text):
    if not text:
        return ""

    text = text.replace("預約", "").replace("時間", "").replace("：", "").replace(" ", "")

    # 1545 → 15:45
    if re.fullmatch(r"\d{3,4}", text):
        if len(text) == 3:
            text = "0" + text
        return f"{text[:2]}:{text[2:]}"

    # 一般時間
    match = re.search(r"(\d{1,2})[:：]?(\d{0,2})", text)
    if match:
        h = match.group(1)
        m = match.group(2) if match.group(2) else "00"
        return f"{int(h)}:{m}"

    return text


# =====================
# 人數加價
# =====================
def calc_fee(pax):
    if pax <= 4:
        return 0
    return (pax - 4) * 100


# =====================
# 主解析
# =====================
def parse_message(text):

    lines = text.split("\n")

    pickup, dropoff = smart_parse(lines)

    pax = 0
    remark = ""
    date = ""
    time = ""

    for line in lines:
        line = line.strip()

        if "乘坐人數" in line:
            nums = re.findall(r"\d+", line)
            pax = int(nums[0]) if nums else 0

        elif "其他備註" in line:
            remark = line.split("：")[-1].strip()

        elif "日期" in line:
            date = parse_date(line.split("：")[-1])

        elif "時間" in line:
            time = parse_time(line.split("：")[-1])

    if not pickup:
        return ""

    output = []

    # 日期 + 時間
    dt = " ".join([x for x in [date, time] if x])
    if dt:
        output.append(dt)

    # 上車
    if pickup:
        output.append(f"⬆️{pickup}")

    # 下車
    if dropoff:
        output.append(f"下車地址：{dropoff}")

    # 底部資訊
    bottom = []

    # 人數（>4 才顯示）
    if pax > 4:
        bottom.append(f"{pax}人 +{calc_fee(pax)}")

    # 備註
    if remark:
        bottom.append(f"✅{remark}")

    if bottom:
        output.append("｜".join(bottom))

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