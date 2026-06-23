from flask import Flask, request
import requests
import os
import re
from datetime import datetime

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

REMOVE_CITIES = ["台北市", "臺北市", "新北市", "桃園市", "北市"]

IGNORE_DATE_WORDS = ["今天", "今日", "當日", "現在", "立即", "馬上", "立刻"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]

IGNORE_REMARKS = ["無", "沒有", "無備註", "不用", "-", "N/A", "n/a", ""]


def clean_postcode(addr: str):
    return re.sub(r"^\d{3,5}\s*", "", addr.strip())


def clean_city(addr: str):
    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")
    return addr.strip()


def clean_address_text(addr):
    addr = clean_postcode(addr)
    addr = clean_city(addr)

    addr = re.sub(r'^(地址[:：]?\s*|上車[:：]?\s*|下車[:：]?\s*)', '', addr)

    return addr.strip()


def format_time(text: str):
    if not text:
        return ""

    t = text.strip()

    if any(w in t for w in IGNORE_TIME_WORDS):
        return ""

    t = t.replace("預約", "")
    return t.strip()


def format_date(text):
    if not text:
        return ""

    t = text.strip()

    if any(w in t for w in IGNORE_DATE_WORDS):
        return ""

    now = datetime.now()

    m = re.match(r"^(\d{1,2})號?$", t)
    if m:
        day = int(m.group(1))
        if day == now.day:
            return ""
        return f"{now.month}/{day}"

    m = re.match(r"^(\d{1,2})/(\d{1,2})$", t)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))

        if month == now.month and day == now.day:
            return ""

        return f"{month}/{day}"

    return t


def parse_people(num_text: str, remark_lines):
    try:
        n = int(num_text)
    except:
        return ""

    if n <= 4:
        return ""

    fee = (n - 4) * 100
    remark = " ".join(remark_lines).strip()

    if remark:
        return f"{n}人 +{fee}｜✅{remark}"
    return f"{n}人 +{fee}"


def extract_remarks(lines, start_idx):
    remarks = []

    for i in range(start_idx, len(lines)):
        t = lines[i].strip()

        if not t:
            continue

        if any(x in t for x in ["電話", "手機", "上車", "下車", "日期", "時間", "人數"]):
            break

        if t in IGNORE_REMARKS:
            continue

        remarks.append(t)

    return remarks


def extract_addresses(lines):
    pickups = []
    dropoffs = []

    for line in lines:
        l = line.strip()

        if not l:
            continue

        if "上車" in l or "⬆️" in l:
            l = l.replace("上車地址：", "").replace("上車：", "").replace("⬆️", "")
            l = clean_address_text(l)
            if l:
                pickups.append(l)

        elif "下車" in l or "⬇️" in l:
            l = l.replace("下車地址：", "").replace("下車：", "").replace("⬇️", "")
            l = clean_address_text(l)
            if l:
                dropoffs.append(l)

    return pickups, dropoffs


def fallback_addresses(lines):
    addrs = []

    for l in lines:
        l = l.strip()

        if not l:
            continue

        if any(x in l for x in ["日期", "時間", "人數", "備註", "電話", "手機"]):
            continue

        if "http" in l:
            continue

        addrs.append(clean_address_text(l))

    if len(addrs) >= 2:
        return [addrs[0]], addrs[1:]

    return addrs, []


@app.route("/")
def home():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    for event in body.get("events", []):

        if event.get("type") != "message":
            continue

        if event["message"]["type"] != "text":
            continue

        text = event["message"]["text"]
        lines = text.split("\n")

        reply_token = event.get("replyToken")

        date = ""
        time = ""
        people = ""
        remark_lines = []

        pickups, dropoffs = extract_addresses(lines)

        if not pickups and not dropoffs:
            pickups, dropoffs = fallback_addresses(lines)

        for i, line in enumerate(lines):
            l = line.strip()

            if "日期" in l:
                date = format_date(l.split("：")[-1])

            elif "時間" in l:
                time = format_time(l.split("：")[-1])

            elif "乘坐人數" in l or "人數" in l:
                people = l.split("：")[-1]

            elif "備註" in l:

                same_line = ""

                if "：" in l:
                    same_line = l.split("：", 1)[1].strip()

                remark_lines = []

                if same_line and same_line not in IGNORE_REMARKS:
                    remark_lines.append(same_line)

                remark_lines.extend(extract_remarks(lines, i + 1))

        output = []

        if date and time:
            output.append(f"{date} {time}")
        elif date:
            output.append(date)
        elif time:
            output.append(time)

        for p in pickups:
            output.append(f"⬆️{p}")

        for d in dropoffs:
            output.append(f"下車地址：{d}")

        people_text = parse_people(people, remark_lines)
        if people_text:
            output.append(people_text)

        final_text = "\n".join(output)

        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": final_text if final_text else "無有效內容"
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