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

IGNORE_TIME_WORDS = [
    "現在", "立即", "馬上", "立刻",
    "即時", "即刻", "隨時"
]

IGNORE_DATE_WORDS = ["今天", "今日", "當日"]

# ======================
# MERGE BROKEN LINES
# ======================

def merge_broken_lines(lines):
    merged = []
    buffer = ""

    for l in lines:
        l = l.strip()
        if not l:
            continue

        # 如果這一行不是新欄位，視為上一行地址/內容延續
        if buffer and not re.search(r"(日期|時間|上車|下車|人數|手機|電話|行李|備註|其他備註|💰|價格)", l):
            buffer += l
        else:
            if buffer:
                merged.append(buffer)
            buffer = l

    if buffer:
        merged.append(buffer)

    return merged

# ======================
# CLEAN ADDRESS
# ======================

def clean_address(addr):
    if not addr:
        return ""

    addr = addr.strip()

    # 只移除開頭郵遞區號，不移除門牌號碼
    addr = re.sub(r"^\d{3,6}\s*", "", addr)

    # 移除指定城市
    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")

    # 移除殘留欄位字
    addr = re.sub(r"^(第?二|第?三)?(上車|下車)(地址|地點)?[:：]?", "", addr)
    addr = re.sub(r"^(地址|地點)[:：]?", "", addr)

    # 清理空白
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

    t = t.replace("預約", "").strip()

    # 0500 / 0600pm / 630am
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

    # 6:30 / 6:30pm / 6:30 AM
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", t)
    if m:
        h = int(m.group(1))
        mi = m.group(2)
        ap = m.group(3)

        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0

        return f"{h:02d}:{mi}"

    # 非時間內容不顯示
    return ""

# ======================
# DATE
# ======================

def format_date(text):
    if not text:
        return ""

    now = datetime.now()
    t = text.strip()

    if any(w in t for w in IGNORE_DATE_WORDS):
        return ""

    # 7/14
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", t)
    if m:
        mo = int(m.group(1))
        d = int(m.group(2))

        if mo == now.month and d == now.day:
            return ""

        return f"{mo}/{d}"

    # 24 / 24號
    m = re.match(r"^(\d{1,2})號?$", t)
    if m:
        d = int(m.group(1))

        if d == now.day:
            return ""

        return f"{now.month}/{d}"

    return ""

# ======================
# ADDRESS PARSER
# ======================

def extract_addresses(lines):
    ups = []
    downs = []

    for raw in lines:
        s = raw.strip()
        if not s:
            continue

        if "上車" in s:
            s = re.sub(r"^(第?二|第?三)?上車(地址|地點)?[:：]?", "", s)
            s = clean_address(s)

            if s:
                ups.append(s)

        elif "下車" in s:
            s = re.sub(r"^(第?二|第?三)?下車(地址|地點)?[:：]?", "", s)
            s = clean_address(s)

            if s:
                downs.append(s)

    return ups, downs

# ======================
# FALLBACK
# ======================

def fallback(lines):
    addresses = []

    for l in lines:
        s = l.strip()
        if not s:
            continue

        if any(x in s for x in ["日期", "時間", "人數", "手機", "電話", "💰", "價格", "備註", "行李"]):
            continue

        cleaned = clean_address(s)
        if cleaned:
            addresses.append(cleaned)

    if len(addresses) == 0:
        return [], []

    if len(addresses) == 1:
        return [addresses[0]], []

    # 沒有標記上下車時：第一個地址=上車，第二個以後=下車/多下車
    return [addresses[0]], addresses[1:]

# ======================
# PEOPLE
# ======================

def parse_people(text):
    try:
        n = int(re.findall(r"\d+", str(text))[0])
    except:
        return ""

    if n <= 4:
        return ""

    return f"{n}人 +{(n - 4) * 100}"

# ======================
# REMARKS
# ======================

def extract_remarks(lines):
    tags = []

    for raw in lines:
        l = raw.strip()
        if not l:
            continue

        # 只抓備註欄位，避免地址/行李/上下車誤進備註
        if "備註" not in l:
            continue

        l = re.sub(r"^(其他)?備註[:：]?", "", l).strip()

        if not l:
            continue

        for p in re.split(r"\s+", l):
            p = p.strip()
            if p:
                tags.append("✅" + p)

    return "".join(tags)

# ======================
# PRICE
# ======================

def extract_price(text):
    if not text:
        return ""

    m = re.search(r"(?:💰|\$|價格|固定)?\s*(\d{3,6})", text)
    if m:
        return f"💰{m.group(1)}"

    return ""

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
                lines = merge_broken_lines(text.split("\n"))

                reply_token = event.get("replyToken")

                date = ""
                time = ""
                people = ""
                price = ""

                ups, downs = extract_addresses(lines)

                if not ups and not downs:
                    ups, downs = fallback(lines)

                for s in lines:
                    s = s.strip()

                    if "日期" in s:
                        m = re.search(r"(\d{1,2}/\d{1,2}|\d{1,2}號?|\d{1,2})", s)
                        if m:
                            date = format_date(m.group(1))
                        elif any(w in s for w in IGNORE_DATE_WORDS):
                            date = ""

                    elif "時間" in s:
                        parts = re.split(r"[:：]", s, 1)
                        if len(parts) > 1:
                            time = format_time(parts[1].strip())
                        else:
                            time = ""

                    elif "人數" in s:
                        m = re.search(r"(\d+)", s)
                        if m:
                            people = m.group(1)

                    elif "💰" in s or "價格" in s or "固定" in s:
                        price = extract_price(s)

                remarks = extract_remarks(lines)

                output = []

                # 日期 + 時間同一行；今天不顯示日期
                if date and time:
                    output.append(f"{date} {time}")
                elif time:
                    output.append(time)
                elif date:
                    output.append(date)

                # 上車
                for u in ups:
                    output.append(f"⬆️：{u}")

                # 下車
                if len(downs) == 1:
                    output.append(f"下車地點：{downs[0]}")
                elif len(downs) > 1:
                    output.append(f"下車地點：{downs[0]}")
                    for d in downs[1:]:
                        output.append(f"🔽{d}")

                # 人數 + 備註
                ptxt = parse_people(people)

                if ptxt and remarks:
                    output.append(f"{ptxt}｜")
                    output.append(remarks)
                elif ptxt:
                    output.append(f"{ptxt}｜")
                elif remarks:
                    output.append(remarks)

                # 價格固定最下方
                if price:
                    output.append(price)

                final = "\n".join(output) or "無內容"

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
                except Exception:
                    print(traceback.format_exc())

            except Exception:
                print(traceback.format_exc())
                continue

        return "OK", 200

    except Exception:
        print(traceback.format_exc())
        return "OK", 200

# ======================
# START
# ======================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000,
        threaded=True
    )
