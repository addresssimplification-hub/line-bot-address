from flask import Flask, request
import requests
import os
import re
from datetime import datetime
import traceback

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# ======================
# CONFIG
# ======================

REMOVE_CITIES = ["台北市", "臺北市", "新北市", "桃園市", "北市"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]
IGNORE_DATE_WORDS = ["今天", "今日", "當日"]

# ======================
# 🔥 新增：合併斷行地址
# ======================

def merge_broken_lines(lines):
    merged = []
    buffer = ""

    for l in lines:
        l = l.strip()
        if not l:
            continue

        # 判斷是否為延續地址
        if buffer and not any(x in l for x in ["上車", "下車", "日期", "時間", "人數", "手機", "電話", "💰", "備註"]):
            buffer += l
        else:
            if buffer:
                merged.append(buffer)
            buffer = l

    if buffer:
        merged.append(buffer)

    return merged

# ======================
# ADDRESS CLEAN
# ======================

def clean_address(addr):
    if not addr:
        return ""

    addr = addr.strip()

    # 郵遞區號
    addr = re.sub(r"^\d{3,6}\s*", "", addr)

    # 城市移除
    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")

    # 標籤移除
    addr = re.sub(r'^(上車|下車|地址|地點|第二|第三)?[:：]?', '', addr)

    # 空白清理
    addr = re.sub(r"\s+", "", addr)

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
# DATE
# ======================

def format_date(text):
    if not text:
        return ""

    t = text.strip()
    now = datetime.now()

    if any(w in t for w in IGNORE_DATE_WORDS):
        return ""

    m = re.match(r"^(\d{1,2})/(\d{1,2})$", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if mo == now.month and d == now.day:
            return ""
        return f"{mo}/{d}"

    m = re.match(r"^(\d{1,2})號?$", t)
    if m:
        d = int(m.group(1))
        if d == now.day:
            return ""
        return f"{now.month}/{d}"

    return t

# ======================
# ADDRESS PARSER
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

# ======================
# FALLBACK（自動上下車）
# ======================

def fallback(lines):
    a = []

    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in ["日期", "時間", "人數", "手機", "電話", "💰"]):
            continue

        cleaned = clean_address(l)
        if cleaned:
            a.append(cleaned)

    if len(a) == 0:
        return [], []

    if len(a) == 1:
        return [a[0]], []

    return [a[0]], a[1:]

# ======================
# PEOPLE
# ======================

def parse_people(n):
    try:
        n = int(n)
    except:
        return ""

    if n <= 4:
        return ""

    return f"{n}人 +{(n-4)*100}"

# ======================
# REMARKS
# ======================

def extract_remarks(lines):
    bad_words = [
        "電話", "手機", "麻煩", "填寫", "提供", "完整", "正確",
        "日期", "時間", "人數", "💰", "地址",
        "上車", "下車", "行李", "乘坐", "第二", "第三"
    ]

    tags = []

    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in bad_words):
            continue

        parts = re.split(r"\s+", l)

        for p in parts:
            if p:
                tags.append("✅" + p)

    return "".join(tags)

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

                # 🔥 先合併斷行
                lines = merge_broken_lines(text.split("\n"))

                reply_token = event.get("replyToken")

                date = ""
                time = ""
                people = ""
                price = ""

                ups, downs = extract_addresses(lines)

                if not ups and not downs:
                    ups, downs = fallback(lines)

                for l in lines:
                    s = l.strip()

                    if "日期" in s:
                        date = format_date(s.split("：")[-1])

                    elif "時間" in s:
                        time = format_time(s.split("：")[-1])

                    elif "人數" in s:
                        people = s.split("：")[-1]

                    elif "💰" in s or "價格" in s:
                        price = extract_price(s)

                # ======================
                # OUTPUT
                # ======================
                output = []

                if date or time:
                    output.append(f"{date} {time}".strip())

                for u in ups:
                    output.append(f"⬆️：{u}")

                if len(downs) == 1:
                    output.append(f"下車地點：{downs[0]}")
                elif len(downs) > 1:
                    output.append(f"下車地點：{downs[0]}")
                    for d in downs[1:]:
                        output.append(f"🔽{d}")

                ptxt = parse_people(people)
                remark_txt = extract_remarks(lines)

                if ptxt and remark_txt:
                    output.append(f"{ptxt}｜")
                    output.append(remark_txt)
                elif ptxt:
                    output.append(f"{ptxt}｜")
                elif remark_txt:
                    output.append(remark_txt)

                if price:
                    output.append(price)

                final = "\n".join(output) or "無內容"

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