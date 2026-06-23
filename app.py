import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage


app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def is_booking_text(text):
    keywords = [
        "上車", "下車", "日期", "時間", "人數",
        "機場", "桃機", "航廈", "悠遊GO", "預約",
        "💰", "$", "＄"
    ]
    return any(k in text for k in keywords)


def clean_line(line):
    line = line.strip()
    line = re.sub(r"^[\s\-—–_]+", "", line)
    line = re.sub(r"^(日期|時間|上車地址|下車地址|上車|下車|第二上車|第三上車|第二下車|第三下車|地址)\s*[:：]?\s*", "", line)
    return line.strip()


def clean_address(addr):
    addr = addr.strip()
    addr = re.sub(r"^\d{3,5}", "", addr)
    addr = re.sub(r"(台北市|臺北市|新北市|桃園市|北市)", "", addr)

    # 移除 XX里
    addr = re.sub(r"[\u4e00-\u9fff]{1,5}里", "", addr)

    addr = re.sub(r"\s+", "", addr)
    return addr.strip()


def parse_date(text):
    today = datetime.now(ZoneInfo("Asia/Taipei"))
    current_month = today.month
    current_day = today.day

    m = re.search(r"日期\s*[:：]?\s*(\d{1,2})/(\d{1,2})", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    m = re.search(r"日期\s*[:：]?\s*(\d{1,2})\s*(號|日)?", text)
    if m:
        day = int(m.group(1))
        if day == current_day:
            return ""
        return f"{current_month}/{day}"

    if any(w in text for w in ["今天", "今日", "當日", "現在", "立即", "馬上", "立刻"]):
        return ""

    return ""


def parse_time(text):
    if re.search(r"(現在|立即|馬上|立刻)", text):
        return ""

    # 時間：早上5:30 / 下午6:30 / 晚上 9:05
    m = re.search(
        r"時間\s*[:：]?\s*(早上|上午|下午|晚上|中午|凌晨)?\s*(\d{1,2})\s*[:：]\s*(\d{2})",
        text,
        re.I
    )
    if m:
        period = m.group(1) or ""
        hour = int(m.group(2))
        minute = int(m.group(3))

        if period in ["下午", "晚上"] and hour < 12:
            hour += 12
        elif period == "中午" and hour < 12:
            hour += 12
        elif period == "凌晨" and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    # 0600pm / 0530am / 0600 pm
    m = re.search(r"時間\s*[:：]?\s*(\d{1,2})(\d{2})\s*(am|pm|AM|PM)", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ap = m.group(3).lower()

        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    # 0500 / 1830
    m = re.search(r"時間\s*[:：]?\s*(\d{1,2})(\d{2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return ""


def parse_price(text):
    m = re.search(r"(?:固定\s*)?(?:💰|[$＄])\s*(\d+)", text)
    if m:
        return f"💰{m.group(1)}"
    return ""


def parse_people(text):
    m = re.search(r"人數\s*[:：]?\s*(.+)", text)
    if not m:
        m = re.search(r"(\d+)\s*人", text)
        if m:
            people = int(m.group(1))
        else:
            return ""

    else:
        raw = m.group(1).strip()

        nums = re.findall(r"(\d+)\s*(大|小|人)?", raw)
        if not nums:
            return ""

        people = 0
        for n, _ in nums:
            people += int(n)

    if people > 4:
        extra = (people - 4) * 100
        return f"{people}人 +{extra}"

    return ""


def parse_notes(text):
    m = re.search(r"備註\s*[:：]?\s*(.*)", text)
    if not m:
        return ""

    note = m.group(1).strip()
    if not note:
        return ""

    note = re.sub(r"[，,、/]+", " ", note)
    parts = [p.strip() for p in note.split() if p.strip()]

    if not parts:
        return ""

    return "".join([f"✅{p}" for p in parts])


def parse_addresses(text):
    pickups = []
    dropoffs = []

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        if re.match(r"^上車\s*[:：]", line) or re.match(r"^上車地址\s*[:：]", line):
            addr = clean_address(clean_line(line))
            if addr:
                pickups.append(addr)

        elif re.match(r"^(第二上車|第三上車)\s*[:：]?", line):
            addr = clean_address(clean_line(line))
            if addr:
                pickups.append(addr)

        elif re.match(r"^下車\s*[:：]", line) or re.match(r"^下車地址\s*[:：]", line):
            addr = clean_address(clean_line(line))
            if addr:
                dropoffs.append(addr)

        elif re.match(r"^(第二下車|第三下車)\s*[:：]?", line):
            addr = clean_address(clean_line(line))
            if addr:
                dropoffs.append(addr)

    # 無標籤雙行地址：第一行上車、第二行下車
    if not pickups and not dropoffs:
        address_like = []
        for line in lines:
            if re.search(r"(市|區|路|街|巷|弄|號|機場|航廈|桃機|T1|T2)", line):
                address_like.append(clean_address(clean_line(line)))

        if len(address_like) >= 2:
            pickups.append(address_like[0])
            dropoffs.append(address_like[1])

    return pickups, dropoffs


def format_booking(text):
    date_text = parse_date(text)
    time_text = parse_time(text)
    price_text = parse_price(text)
    people_text = parse_people(text)
    note_text = parse_notes(text)
    pickups, dropoffs = parse_addresses(text)

    output = []

    dt = " ".join([x for x in [date_text, time_text] if x])
    if dt:
        output.append(dt)

    for p in pickups:
        output.append(f"⬆️：{p}")

    if dropoffs:
        output.append(f"下車地點：{dropoffs[0]}")
        for d in dropoffs[1:]:
            output.append(f"🔽{d}")

    line = ""
    if people_text:
        line += people_text
    if note_text:
        if line:
            line += "｜" + note_text
        else:
            line += "｜" + note_text

    if line:
        output.append(line)

    if price_text:
        output.append(price_text)

    return "\n".join(output).strip()


@app.route("/", methods=["GET"])
def home():
    return "LINE Bot is running"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print("Callback error:", e)
        abort(500)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()

    if not is_booking_text(text):
        return

    result = format_booking(text)

    if not result:
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=result)
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))