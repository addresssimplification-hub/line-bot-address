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

    t = text.strip()

    if any(w in t for w in IGNORE_TIME_WORDS):
        return ""

    m = re.search(r"(\d{1,2}):?(\d{0,2})\s*(am|pm)?", t.lower())
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
# PEOPLE
# ======================
def parse_people(n):
    try:
        n = int(re.search(r"\d+", str(n)).group())
    except:
        return ""

    if n <= 4:
        return f"{n}人"

    fee = (n - 4) * 100
    return f"{n}人（+{fee}）"


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
# ADDRESSES (AUTO SORT)
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
                up_map[num if num else len(up_map)+1] = addr

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
                down_map[num if num else len(down_map)+1] = addr

    ups = [up_map[k] for k in sorted(up_map.keys())]
    downs = [down_map[k] for k in sorted(down_map.keys())]

    return ups, downs


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
                is_nosmoke = False

                ups, downs = extract_addresses(lines)

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
                        r = s.replace("備註：", "").replace("備註:", "").strip()
                        if r:
                            if "禁煙" in r:
                                is_nosmoke = True
                            else:
                                remarks.append(r)

                    if "禁煙" in s:
                        is_nosmoke = True

                # ======================
                # OUTPUT BUILD
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

                ppl = parse_people(people)

                people_line = []
                if ppl:
                    people_line.append(ppl)
                if is_nosmoke:
                    people_line.append("✅ 禁煙")

                if people_line:
                    output.append("👥 " + " ｜ ".join(people_line))

                if remarks:
                    output.append("｜" + " ".join(remarks))

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