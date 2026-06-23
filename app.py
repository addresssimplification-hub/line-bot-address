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

IGNORE_DATE_WORDS = ["今天", "今日", "當日", "現在", "立即", "馬上", "立刻"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]


# ======================
# CLEAN ADDRESS
# ======================
def clean_address(addr):
    if not addr:
        return ""

    addr = re.sub(r"^\d{3,5}\s*", "", addr.strip())

    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")

    addr = re.sub(r'^(上車|下車|地址|第一|第二|第三|第四|第五)?[:：]?', '', addr)

    return addr.strip()


# ======================
# TIME
# ======================
def format_time(text):
    if not text:
        return ""

    t = text.strip()

    if any(w in t for w in IGNORE_TIME_WORDS):
        return ""

    t = t.replace("預約", "").strip()

    m = re.search(r"下午\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)) + 12:02d}:00"

    m = re.search(r"晚上\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)) + 12:02d}:00"

    m = re.search(r"傍晚\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)) + 12:02d}:00"

    m = re.search(r"早上|上午\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)):02d}:00"

    m = re.search(r"凌晨\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)):02d}:00"

    m = re.match(r"^(\d{3,4})\s*(am|pm)?$", t.lower())
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
# PEOPLE
# ======================
def parse_people(n):
    try:
        n = int(re.search(r"\d+", str(n)).group())
    except:
        return ""

    if n <= 4:
        return ""

    fee = (n - 4) * 100
    return f"{n}人 +{fee}"


# ======================
# PRICE
# ======================
def extract_price(text):
    if not text:
        return ""

    m = re.search(r"(?:💰|\$|價格)?\s*(\d{3,6})", text)
    if m:
        return f"💰{m.group(1)}"

    return ""


# ======================
# REMARKS
# ======================
def extract_remarks(lines):
    r = []
    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in ["電話", "手機", "上車", "下車", "日期", "時間", "人數", "💰"]):
            continue

        r.append(l)

    return r


# ======================
# 🚀 AUTO SORT ADDRESSES
# ======================
def extract_addresses(lines):
    up_map = {}
    down_map = {}

    num_map = {
        "第一": 1,
        "第二": 2,
        "第三": 3,
        "第四": 4,
        "第五": 5
    }

    for l in lines:
        s = l.strip()
        if not s:
            continue

        # ========= 上車 =========
        if "上車" in s:
            num = None

            for k, v in num_map.items():
                if k in s:
                    num = v
                    break

            addr = re.sub(r"(第一|第二|第三|第四|第五)?上車(地址)?[:：]?", "", s)
            addr = clean_address(addr)

            if addr:
                if num:
                    up_map[num] = addr
                else:
                    up_map[len(up_map) + 1] = addr

        # ========= 下車 =========
        elif "下車" in s:
            num = None

            for k, v in num_map.items():
                if k in s:
                    num = v
                    break

            addr = re.sub(r"(第一|第二|第三|第四|第五)?下車(地址)?[:：]?", "", s)
            addr = clean_address(addr)

            if addr:
                if num:
                    down_map[num] = addr
                else:
                    down_map[len(down_map) + 1] = addr

    ups = [up_map[k] for k in sorted(up_map.keys())]
    downs = [down_map[k] for k in sorted(down_map.keys())]

    return ups, downs


def fallback(lines):
    a = []
    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in ["日期", "時間", "人數", "備註", "電話", "手機"]):
            continue

        a.append(clean_address(l))

    if len(a) >= 2:
        return [a[0]], a[1:]

    return a, []


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

                date = ""
                time = ""
                people = ""
                price = ""
                remarks = []

                ups, downs = extract_addresses(lines)

                if not ups and not downs:
                    ups, downs = fallback(lines)

                for s in lines:
                    s = s.strip()

                    if "日期" in s:
                        date = format_date(s.split("：")[-1])

                    elif "時間" in s:
                        time = format_time(s.split("：")[-1])

                    elif "人數" in s:
                        people = s.split("：")[-1]

                    elif "💰" in s or "價格" in s:
                        price = extract_price(s)

                    elif re.fullmatch(r"\d{3,6}", s):
                        price = f"💰{s}"

                    elif "備註" in s:
                        remark = s.replace("備註：", "").replace("備註:", "").strip()
                        if remark and remark not in ["無", "沒有", "無備註"]:
                            remarks.append(remark)

                remarks.extend(extract_remarks(lines))

                output = []

                if date and time:
                    output.append(f"{date} {time}")
                elif date:
                    output.append(date)
                elif time:
                    output.append(time)

                for i, u in enumerate(ups, 1):
                    output.append(f"⬆️上車{i}：{u}")

                for i, d in enumerate(downs, 1):
                    output.append(f"⬇️下車{i}：{d}")

                ptxt = parse_people(people)
                if ptxt:
                    output.append(ptxt)

                if remarks:
                    output.append("｜✅ " + " ".join(remarks))

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


# ======================
# START
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, threaded=True)