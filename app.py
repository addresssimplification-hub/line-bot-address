from flask import Flask, request
import requests
import os
import re
from datetime import datetime
import traceback

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# ======================
# HEALTH CHECK
# ======================

@app.route("/")
def home():
    return "OK"

@app.route("/ping")
def ping():
    return "alive"

# ======================
# CONFIG
# ======================

REMOVE_CITIES = ["台北市", "臺北市", "新北市", "桃園市", "北市"]

IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]

# ======================
# CLEAN ADDRESS
# ======================

def clean_address(addr):
    addr = re.sub(r"^\d{3,5}\s*", "", addr.strip())
    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")
    addr = re.sub(r'^(上車|下車|地址|第二|第三)?[:：]?', '', addr)
    return addr.strip()

# ======================
# TIME
# ======================

def format_time(text):
    if not text:
        return ""

    t = text.strip().lower()

    if any(w in t for w in IGNORE_TIME_WORDS):
        return ""

    m = re.match(r"^(\d{3,4})\s*(am|pm)?$", t)
    if m:
        num = m.group(1)
        ap = m.group(2)

        if len(num) == 3:
            num = "0" + num

        h = int(num[:2])
        mi = num[2:]

        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0

        return f"{h:02d}:{mi}"

    return t

# ======================
# ADDRESS
# ======================

def extract_addresses(lines):
    ups = []
    downs = []

    for l in lines:
        s = l.strip()
        if not s:
            continue

        if "上車" in s:
            s = re.sub(r"(第二|第三)?上車[:：]?", "", s)
            s = clean_address(s)
            if s:
                ups.append(s)

        elif "下車" in s:
            s = s.replace("下車地址：", "").replace("下車：", "")
            s = clean_address(s)
            if s:
                downs.append(s)

    return ups, downs

# fallback
def fallback(lines):
    a = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if any(x in l for x in ["日期", "時間", "人數", "備註", "電話", "手機", "💰"]):
            continue
        a.append(clean_address(l))

    if len(a) >= 2:
        return [a[0]], a[1:]

    return a, []

# ======================
# CLEAN REMARKS (重點修正)
# ======================

def extract_remarks(lines):
    bad_words = [
        "電話", "手機", "上車", "下車", "日期", "時間", "人數", "💰",
        "麻煩填寫", "麻煩提供", "正確電話", "完整地址"
    ]

    r = []
    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in bad_words):
            continue

        r.append(l)

    return r

# ======================
# PRICE
# ======================

def extract_price(text):
    if not text:
        return ""

    m = re.search(r"(?:💰|\$)?\s*(\d{3,6})", text)
    if m:
        return f"💰{m.group(1)}"

    return ""

# ======================
# CALLBACK
# ======================

@app.route("/callback", methods=["POST"])
def callback():
    try:
        body = request.get_json(force=True)

        for event in body.get("events", []):

            try:
                if event.get("type") != "message":
                    continue

                if event["message"]["type"] != "text":
                    continue

                text = event["message"]["text"]
                lines = text.split("\n")
                reply_token = event.get("replyToken")

                time = ""
                price = ""

                ups, downs = extract_addresses(lines)

                if not ups and not downs:
                    ups, downs = fallback(lines)

                remarks = []

                for i, l in enumerate(lines):
                    s = l.strip()

                    if "時間" in s:
                        time = format_time(s.split("：")[-1])

                    elif "💰" in s or "價格" in s:
                        price = extract_price(s)

                    elif "備註" in s:
                        remarks = extract_remarks(lines[i+1:])

                # ======================
                # OUTPUT (你要的格式)
                # ======================
                output = []

                if time:
                    output.append(time)

                for u in ups:
                    output.append(f"⬆️上車：{u}")

                for d in downs:
                    output.append(f"下車地址：{d}")

                if remarks:
                    output.append("✅" + " ".join(remarks))

                if price:
                    output.append(price)

                final = "\n".join(output) or "無內容"

                # reply LINE
                try:
                    requests.post(
                        "https://api.line.me/v2/bot/message/reply",
                        headers={
                            "Authorization": f"Bearer {TOKEN}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "replyToken": reply_token,
                            "messages": [{"type": "text", "text": final}]
                        },
                        timeout=5
                    )
                except:
                    pass

            except Exception:
                print(traceback.format_exc())
                continue

        return "OK", 200

    except Exception:
        print(traceback.format_exc())
        return "OK", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000,
        threaded=True
    )