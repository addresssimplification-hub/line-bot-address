from flask import Flask, request
import requests
import os
import re
from datetime import datetime

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

# ========= 基本設定 =========

REMOVE_CITIES = ["台北市", "臺北市", "新北市", "桃園市", "北市"]

IGNORE_DATE_WORDS = ["今天", "今日", "當日", "現在", "立即", "馬上", "立刻"]
IGNORE_TIME_WORDS = ["現在", "立即", "馬上", "立刻"]

IGNORE_REMARKS = ["無", "沒有", "無備註", "不用", "-", "N/A", "n/a", ""]

# ========= 工具 =========

def clean_postcode(addr: str):
    return re.sub(r"^\d{3,5}\s*", "", addr.strip())


def clean_city(addr: str):
    for c in REMOVE_CITIES:
        addr = addr.replace(c, "")
    return addr.strip()


def format_time(text: str):
    if not text:
        return ""

    t = text.strip()

    if any(w in t for w in IGNORE_TIME_WORDS):
        return ""

    # 移除「預約」
    t = t.replace("預約", "")

    # AM/PM / 上午下午直接保留
    return t.strip()


def format_date(text: str):
    if not text:
        return ""

    t = text.strip()

    if any(w in t for w in IGNORE_DATE_WORDS):
        return ""

    today = datetime.now().strftime("%m/%d")

    # 如果剛好是今天
    if t == today:
        return ""

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

        # 上車
        if "上車" in l or "⬆️" in l:
            l = l.replace("上車地址：", "").replace("上車：", "").replace("⬆️", "")
            l = clean_postcode(clean_city(l))
            if l:
                pickups.append(l)

        # 下車
        elif "下車" in l or "⬇️" in l:
            l = l.replace("下車地址：", "").replace("下車：", "").replace("⬇️", "")
            l = clean_postcode(clean_city(l))
            if l:
                dropoffs.append(l)

    return pickups, dropoffs


def fallback_addresses(lines):
    """沒有標籤時用 fallback（兩段式）"""
    addrs = []

    for l in lines:
        l = l.strip()
        if not l:
            continue
        if any(x in l for x in ["日期", "時間", "人數", "備註", "電話", "手機"]):
            continue
        if "http" in l:
            continue
        addrs.append(clean_postcode(clean_city(l)))

    if len(addrs) >= 2:
        return [addrs[0]], addrs[1:]

    return addrs, []


# ========= LINE =========

@app.route("/")
def home():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    print("BODY =", body)

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

        # fallback（沒標籤）
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
                remark_lines = extract_remarks(lines, i + 1)

        # ========= 組輸出 =========

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

        r = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

        print("LINE API:", r.status_code, r.text)

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)