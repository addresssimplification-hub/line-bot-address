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
IGNORE_DATE_WORDS = ["今天", "今日", "當日", "現在", "立即", "馬上", "立刻"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]

IGNORE_REMARK_WORDS = [
    "電話", "手機", "人數", "行李", "日期", "時間",
    "上車", "下車", "💰", "價格", "麻煩", "請", "填寫", "提供"
]


# ======================
# CLEAN ADDRESS
# ======================
def clean_address(addr):
    if not addr:
        return ""

    addr = re.sub(r"^\d{3,5}\s*", "", addr.strip())
    addr = re.sub(r'^(上車|下車|地址|第一|第二|第三|第四|第五)?[:：]?', '', addr)

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

    m = re.search(r"(\d{1,2}):?(\d{0,2})\s*(am|pm)?", t)
    if m:
        h = int(m.group(1))
        mi = m.group(2) if m.group(2) else "00"
        ap = m.group(3)

        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0

        return f"{h:02d}:{int(mi):02d}"

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
        return f"{m.group(1)}/{m.group(2)}"

    m = re.match(r"^(\d{1,2})號?$", t)
    if m:
        return f"{now.month}/{m.group(1)}"

    return t


# ======================
# PEOPLE (ONLY >=5 SHOW)
# ======================
def format_people(n):
    try:
        n = int(re.search(r"\d+", str(n)).group())
    except:
        return None

    if n < 5:
        return None

    fee = (n - 4) * 100
    return f"👥 {n}人（+{fee}）"


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
# ADDRESSES
# ======================
def extract_addresses(lines):
    up = []
    down = []

    for l in lines:
        s = l.strip()
        if not s:
            continue

        if "上車" in s:
            addr = re.sub(r"(第一|第二|第三|第四|第五)?上車(地址)?[:：]?", "", s)
            addr = clean_address(addr)
            if addr:
                up.append(addr)

        elif "下車" in s:
            addr = re.sub(r"(第一|第二|第三|第四|第五)?下車(地址)?[:：]?", "", s)
            addr = clean_address(addr)
            if addr:
                down.append(addr)

    return up, down


# ======================
# REMARKS (NO POLLUTION)
# ======================
def extract_remarks(lines):
    r = []

    for l in lines:
        l = l.strip()
        if not l:
            continue

        if any(x in l for x in IGNORE_REMARK_WORDS):
            continue

        if "備註" in l:
            v = l.replace("備註：", "").replace("備註:", "").strip()
            if v and v != "無":
                r.append(v)
            continue

        # 過濾純提示句
        if "‼️" in l:
            continue

        r.append(l)

    return r


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
                is_nosmoke = False

                ups, downs = extract_addresses(lines)
                remarks = extract_remarks(lines)

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

                    if "禁煙" in s:
                        is_nosmoke = True

                # ======================
                # OUTPUT
                # ======================
                output = []

                if date and time:
                    output.append(f"{date} {time}")
                elif date:
                    output.append(date)
                elif time:
                    output.append(time)

                output.append("")

                for u in ups:
                    output.append(f"⬆️上車：{u}")

                for d in downs:
                    output.append(f"⬇️下車：{d}")

                output.append("")

                ppl = format_people(people)

                tags = []
                if ppl:
                    tags.append(ppl)
                if is_nosmoke:
                    tags.append("✅ 禁煙")

                if tags:
                    output.append(" ".join(tags))

                if remarks:
                    clean_r = [r for r in remarks if r not in ["其他", "其他備註", "無"]]
                    if clean_r:
                        output.append("｜" + " ".join(clean_r))

                if price:
                    output.append("")
                    output.append(price)

                final = "\n".join(output).strip() or "無內容"

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