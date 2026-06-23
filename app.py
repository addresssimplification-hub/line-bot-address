from flask import Flask, request
import requests
import os
import re
from datetime import datetime
import traceback

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

REMOVE_CITIES = ["台北市", "臺北市", "新北市", "桃園市", "北市"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]
IGNORE_DATE_WORDS = ["今天", "今日", "當日"]


def merge_broken_lines(lines):
    merged = []
    buffer = ""

    for l in lines:
        l = l.strip()
        if not l:
            continue

        if buffer and not re.search(r"(日期|時間|上車|下車|人數|手機|電話|行李|備註|其他備註|💰)", l):
            buffer += l
        else:
            if buffer:
                merged.append(buffer)
            buffer = l

    if buffer:
        merged.append(buffer)

    return merged


def clean_address(addr):
    if not addr:
        return ""

    addr = addr.strip()

    addr = re.sub(r"^\d{3,6}\s*", "", addr)

    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")

    addr = re.sub(r"\s+", "", addr)

    return addr.strip()


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

    return t


def format_date(text):
    if not text:
        return ""

    now = datetime.now()
    text = text.strip()

    if any(x in text for x in IGNORE_DATE_WORDS):
        return ""

    m = re.match(r"^(\d{1,2})/(\d{1,2})$", text)
    if m:
        mo = int(m.group(1))
        d = int(m.group(2))

        if mo == now.month and d == now.day:
            return ""

        return f"{mo}/{d}"

    m = re.match(r"^(\d{1,2})號?$", text)
    if m:
        d = int(m.group(1))

        if d == now.day:
            return ""

        return f"{now.month}/{d}"

    return ""


def extract_addresses(lines):
    ups = []
    downs = []

    for s in lines:
        s = s.strip()

        if "上車" in s:
            s = re.sub(r"(第?二|第?三)?上車地址?[:：]?", "", s)
            s = clean_address(s)
            if s:
                ups.append(s)

        elif "下車" in s:
            s = re.sub(r"(第?二|第?三)?下車地址?[:：]?", "", s)
            s = re.sub(r"^\d{3,6}", "", s)
            s = clean_address(s)

            if s:
                downs.append(s)

    return ups, downs


def fallback(lines):
    a = []

    for l in lines:
        if any(x in l for x in ["日期", "時間", "人數", "手機", "電話", "💰", "備註", "行李"]):
            continue

        cleaned = clean_address(l)
        if cleaned:
            a.append(cleaned)

    if len(a) >= 2:
        return [a[0]], [a[1]]

    return a, []


def parse_people(text):
    try:
        n = int(re.findall(r"\d+", str(text))[0])
    except:
        return ""

    if n <= 4:
        return ""

    return f"{n}人 +{(n-4)*100}"


def extract_remarks(lines):
    tags = []

    for l in lines:
        l = l.strip()

        if "備註" in l:
            l = re.sub(r"^(其他)?備註[:：]?", "", l).strip()

            for p in re.split(r"\s+", l):
                if p:
                    tags.append("✅" + p)

    return "".join(tags)


def extract_price(text):
    m = re.search(r"(?:💰|\$)?\s*(\d{3,6})", text)
    if m:
        return f"💰{m.group(1)}"
    return ""


@app.route("/")
def home():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    try:
        body = request.get_json(force=True)

        for event in body.get("events", []):

            if event.get("type") != "message":
                continue

            if event["message"]["type"] != "text":
                continue

            text = event["message"]["text"]
            lines = merge_broken_lines(text.split("\n"))

            date = ""
            time = ""
            people = ""
            price = ""

            ups, downs = extract_addresses(lines)

            if not ups and not downs:
                ups, downs = fallback(lines)

            for s in lines:

                if "日期" in s:
                    m = re.search(r"(\d{1,2}/\d{1,2}|\d{1,2}號?|\d{1,2})", s)
                    if m:
                        date = format_date(m.group(1))

                elif "時間" in s:
                    value = re.split(r"[:：]", s, 1)
                    if len(value) > 1:
                        time = format_time(value[1].strip())

                elif "人數" in s:
                    m = re.search(r"(\d+)", s)
                    if m:
                        people = m.group(1)

                elif "💰" in s or "價格" in s:
                    price = extract_price(s)

            remarks = extract_remarks(lines)

            output = []

            if date and time:
                output.append(f"{date} {time}")
            elif time:
                output.append(time)
            elif date:
                output.append(date)

            for u in ups:
                output.append(f"⬆️：{u}")

            if len(downs) == 1:
                output.append(f"下車地點：{downs[0]}")
            elif len(downs) > 1:
                output.append(f"下車地點：{downs[0]}")
                for d in downs[1:]:
                    output.append(f"🔽{d}")

            ptxt = parse_people(people)

            if ptxt and remarks:
                output.append(f"{ptxt}｜")
                output.append(remarks)
            elif ptxt:
                output.append(f"{ptxt}｜")
            elif remarks:
                output.append(remarks)

            if price:
                output.append(price)

            final = "\n".join(output) if output else "無內容"

            requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "replyToken": event["replyToken"],
                    "messages": [{"type": "text", "text": final}]
                },
                timeout=5
            )

        return "OK", 200

    except Exception:
        print(traceback.format_exc())
        return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, threaded=True)
