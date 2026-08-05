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

BOT_VERSION = "v3.0.5"
GROUP_ID = "C68622c8e7215bffc165b1f657c148b4e"


def notify_startup():
    try:
        now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
        line_bot_api.push_message(
            GROUP_ID,
            TextSendMessage(
                text=f"系統已啟動 ✅\nCC專屬助理已上線 ✅\n有任何問題請洽CC北鼻✅\n版本：{BOT_VERSION}\n時間：{now}"
            )
        )
    except Exception as e:
        print("Startup notify error:", e)




def is_booking_text(text):
    keywords = [
        "上車", "下車", "上車地", "下車地", "上車地點", "下車地點",
        "⬆️", "🔽", "🔺", "🔻",
        "出發", "起點", "到達", "終點",
        "目的", "目的地", "目的●",
        "日期", "時間", "人數", "乘坐人數", "乘車人數",
        "機場", "桃機", "航廈", "預約",
        "接機", "送機", "航班",
        "💰", "$", "＄", "固定"
    ]

    if any(k in text for k in keywords):
        return True

    if re.search(r"(^|\n)\s*(上|下|起)\s*[:： ]", text):
        return True

    if re.search(r"(^|\n)\s*\d{1,2}[/-]\d{1,2}\s+\d{4}\s*($|\n)", text):
        return True

    if re.search(r"(?m)^\s*\d{1,2}[:：]\d{2}\s*$", text):
        return True

    return False


def clean_line(line):
    line = line.strip()
    line = re.sub(r"^[\s\-—–_]+", "", line)
    line = re.sub(
        r"^(日期|時間|第一個上車點|第二個上車點|第三個上車點|"
        r"第一個下車點|第二個下車點|第三個下車點|"
        r"第二上車|第三上車|第二下車|第三下車|"
        r"上車地址|下車地址|上車地點|下車地點|上車地|下車地|"
        r"上車|下車|出發|起點|到達|終點|目的地|目的●|目的|"
        r"上|下|起|地址|🔺上車|🔻下車|⬆️|🔽|🔺|🔻)"
        r"\s*[:：●]?\s*",
        "",
        line
    )
    return line.strip()


def clean_address(addr):
    addr = addr.strip()
    addr = re.sub(r"^[：:●\s]+", "", addr)
    addr = re.sub(r"^\d{3,5}", "", addr)

    addr = re.sub(
        r"^(台北市|臺北市|新北市|桃園市|北市)",
        "",
        addr
    )

    addr = re.sub(
        r"^(台北|臺北|新北)(?=[\u4e00-\u9fff]{1,4}區)",
        "",
        addr
    )

    addr = re.sub(r"(?<=[區鄉鎮市])[\u4e00-\u9fff]{1,6}里", "", addr)
    addr = re.sub(r"(第一|第二)航(?!廈)", r"\1航廈", addr)

    if re.fullmatch(r"第一航廈", addr):
        addr = "桃園第一航廈"
    elif re.fullmatch(r"第二航廈", addr):
        addr = "桃園第二航廈"
    elif re.fullmatch(r"(?i:T1)", addr):
        addr = "桃園第一航廈"
    elif re.fullmatch(r"(?i:T2)", addr):
        addr = "桃園第二航廈"

    districts = [
        "中山", "松山", "大同", "萬華", "信義", "內湖", "南港",
        "士林", "北投", "文山", "中正", "大安",
        "板橋", "新莊", "三重", "中和", "永和", "土城", "樹林",
        "汐止", "蘆洲", "泰山", "林口", "淡水", "新店", "五股",
        "深坑", "三峽", "鶯歌", "瑞芳", "金山", "萬里",
        "中壢", "平鎮", "八德", "龜山", "蘆竹", "大溪", "楊梅",
        "龍潭", "大園", "觀音", "新屋"
    ]
    for district in sorted(districts, key=len, reverse=True):
        if re.match(rf"^{district}(?!區)", addr):
            addr = district + "區" + addr[len(district):]
            break

    addr = re.sub(r"\s+", "", addr)
    return addr.strip()


def parse_date(text):
    today = datetime.now(ZoneInfo("Asia/Taipei"))
    current_month = today.month
    current_day = today.day

    date_label = r"日期(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    if re.search(
        rf"{date_label}\s*[:：]?\s*(當日免填|今日免填|今天|今日|現在|立即|馬上|立刻)",
        text
    ):
        return ""

    m = re.search(
        rf"{date_label}\s*[:：]?\s*(\d{{4}})[/-](\d{{1,2}})[/-](\d{{1,2}})",
        text
    )
    if m:
        month = int(m.group(2))
        day = int(m.group(3))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    m = re.search(
        rf"{date_label}\s*[:：]?\s*(\d{{1,2}})[/-](\d{{1,2}})",
        text
    )
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    m = re.search(
        rf"{date_label}\s*[:：]?\s*(\d{{1,2}})\s*(號|日)?",
        text
    )
    if m:
        day = int(m.group(1))
        if day == current_day:
            return ""
        return f"{current_month}/{day}"

    m = re.search(r"(?m)^\s*(\d{1,2})[/-](\d{1,2})(?=\s+\d{4}\s*$)", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    return ""

def convert_time(period, hour, minute):
    if period in ["下午", "晚上"] and hour < 12:
        hour += 12
    elif period == "中午" and hour < 12:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"




def parse_time(text):
    time_label = r"時間(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    if re.search(
        rf"{time_label}\s*[:：]?\s*(現在|即時免填|現在免填|立即|馬上|立刻|24H|24h|全天|全天候)?\s*$",
        text,
        re.MULTILINE
    ):
        return ""

    m = re.search(
        r"預約\s*[:：]?\s*(\d{1,2})\s*[:：]\s*(\d{2})",
        text
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    m = re.search(
        rf"{time_label}\s*[:：]?\s*(\d{{1,2}})\s*[:：]\s*(\d{{2}})\s*(am|pm)",
        text,
        re.I
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ap = m.group(3).lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    m = re.search(
        rf"{time_label}\s*[:：]?\s*(早上|上午|下午|晚上|中午|凌晨)?\s*(\d{{1,2}})\s*[:：]\s*(\d{{2}})",
        text,
        re.I
    )
    if m:
        return convert_time(m.group(1) or "", int(m.group(2)), int(m.group(3)))

    m = re.search(
        rf"{time_label}\s*[:：]?\s*(早上|上午|下午|晚上|中午|凌晨)?\s*(\d{{1,2}})\s*點",
        text,
        re.I
    )
    if m:
        return convert_time(m.group(1) or "", int(m.group(2)), 0)

    m = re.search(
        rf"{time_label}\s*[:：]?\s*(\d{{1,2}})(\d{{2}})\s*(am|pm)",
        text,
        re.I
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ap = m.group(3).lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    m = re.search(rf"{time_label}\s*[:：]?\s*(\d{{1,2}})(\d{{2}})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    m = re.search(r"(?m)^\s*\d{1,2}[/-]\d{1,2}\s+(\d{2})(\d{2})\s*$", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    m = re.search(r"(?m)^\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*$", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return ""

def parse_price(text):
    patterns = [
        r"固定\s*💰?\s*(\d+)",
        r"💰\s*(\d+)",
        r"[$＄]\s*(\d+)"
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return f"💰{m.group(1)}"

    return ""


def chinese_num_to_int(s):
    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "兩": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10
    }

    if s.isdigit():
        return int(s)

    if s == "十":
        return 10

    if "十" in s:
        parts = s.split("十")
        tens = mapping.get(parts[0], 1) if parts[0] else 1
        ones = mapping.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones

    return mapping.get(s, 0)




def parse_people_count(text):
    m = re.search(
        r"^(?:人數|乘坐人數|乘車人數)\s*[:：]?\s*(.*)$",
        text,
        re.MULTILINE
    )

    raw = ""
    if m:
        raw = m.group(1).strip()
    else:
        m = re.search(
            r"^(?:備註|其他備註)\s*[:：]?\s*.*?([0-9一二兩三四五六七八九十]+)\s*(?:個)?人",
            text,
            re.MULTILINE
        )
        if m:
            raw = m.group(1) + "人"
        else:
            m = re.search(r"([0-9一二兩三四五六七八九十]+)\s*人", text)
            if m:
                raw = m.group(1) + "人"

    if not raw:
        return 0

    nums = re.findall(
        r"([0-9一二兩三四五六七八九十]+)\s*(大|小|人)?",
        raw
    )
    if not nums:
        return 0

    people = sum(chinese_num_to_int(n) for n, _ in nums)
    if people <= 0 or people > 20:
        return 0

    return people

def parse_people(text):
    people = parse_people_count(text)

    if people > 4:
        extra = (people - 4) * 100
        return f"{people}人 +{extra}"

    return ""


def parse_luggage(text):
    m = re.search(
        r"^(?:行李數量|行李數)\s*[:：]?\s*(.*)$",
        text,
        re.MULTILINE
    )
    raw = m.group(1).strip() if m else ""

    if not raw:
        m = re.search(
            r"((?:\d+\s*(?:個|件)?\s*(?:\d{2}吋)?\s*)+行李|"
            r"\d{2}吋\s*\d+\s*(?:個|件)|"
            r"\d+\s*(?:個|件))",
            text
        )
        raw = m.group(1).strip() if m else ""

    if not raw or raw in ["0", "無", "沒有", "無行李", "沒行李"]:
        return ""

    if re.fullmatch(r"\d+", raw):
        return f"🧳{int(raw)}件"

    m = re.fullmatch(r"\s*(\d+)\s*大\s*(\d+)\s*小\s*", raw)
    if m:
        total = int(m.group(1)) + int(m.group(2))
        return f"🧳{total}件"

    size_items = re.findall(r"(\d{2})\s*吋\s*(\d+)\s*(?:個|件)?", raw)
    if size_items:
        total = sum(int(count) for _, count in size_items)
        return f"🧳{total}件"

    nums = [int(n) for n in re.findall(r"(\d+)\s*(?:個|件)", raw)]
    if nums:
        return f"🧳{sum(nums)}件"

    return ""

def parse_notes(text):
    lines = text.splitlines()

    ignore_notes = [
        "0",
        "無", "沒有", "無備註",
        "無行李", "沒行李",
        "免備註", "不用", "正常", "一般", "皆可",
        "N", "n", "NO", "No", "no",
        "-", "--", "免"
    ]

    for line in lines:
        if re.match(r"^\s*(備註|其他備註)\s*[:：]?", line):
            note = re.sub(
                r"^\s*(備註|其他備註)\s*[:：]?\s*",
                "",
                line
            ).strip()

            if not note or note in ignore_notes:
                return ""

            note = re.sub(r"(^|[\s，,、/]+)(接機|送機)(?=$|[\s，,、/]+)", " ", note)
            note = re.sub(
                r"([0-9一二兩三四五六七八九十]+)\s*(?:個)?人",
                " ",
                note
            )
            note = re.sub(
                r"\d{2}\s*吋\s*\d+\s*(?:個|件)?(?:行李)?",
                " ",
                note
            )
            note = re.sub(
                r"\d+\s*(?:個|件)\s*(?:\d{2}\s*吋)?\s*行李",
                " ",
                note
            )

            if re.search(r"^(?:💰|[$＄]|固定)\s*\d+", note.strip()):
                return ""

            note = re.sub(r"[，,、/]+", " ", note)
            parts = [p.strip() for p in note.split() if p.strip()]

            parts = [
                p for p in parts
                if p not in ignore_notes
                and not re.search(r"^(?:💰|[$＄]|固定)\s*\d+", p)
            ]

            if not parts:
                return ""

            return "".join([f"✅{p}" for p in parts])

    return ""


def parse_airport_info(text):
    service_type = ""

    m = re.search(
        r"(?:接機\s*[／/]\s*送機|接機送機)\s*[:：]?\s*(接機|送機)",
        text
    )
    if m:
        service_type = m.group(1)
    else:
        m = re.search(
            r"^(?:備註|其他備註)\s*[:：]?\s*.*?(接機|送機)",
            text,
            re.MULTILINE
        )
        if m:
            service_type = m.group(1)

    flight = ""
    m = re.search(
        r"(?:航班|航班編號|航班號碼)\s*[:：]?[^\n]*?"
        r"([A-Za-z0-9]{2,3}\s*\d{2,4})",
        text,
        re.I
    )
    if m:
        flight = re.sub(r"\s+", "", m.group(1)).upper()

    return service_type, flight


def is_airport_booking(text, service_type, pickups, dropoffs):
    if service_type in ["接機", "送機"]:
        return True

    combined = "\n".join(pickups + dropoffs) + "\n" + text
    return bool(
        re.search(
            r"(桃園機場|桃機|第一航廈|第二航廈|T1|T2|機場)",
            combined,
            re.I
        )
    )

def parse_addresses(text):
    pickups = []
    dropoffs = []

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    stop_keywords = re.compile(
        r"^(日期|時間|人數|乘坐人數|乘車人數|手機號碼|連絡電話|聯絡電話|電話|TEL|"
        r"行李數量|行李數|航班|接機／送機|接機/送機|備註|其他備註|固定|💰|[$＄])"
        r"\s*(?:\([^)]*\)|（[^）]*）)?\s*[:：]?",
        re.I
    )

    pickup_label = (
        r"^(第一個上車點|第二個上車點|第三個上車點|第二上車|第三上車|"
        r"上車地址|上車地點|上車地|上車|出發|起點|起|上|"
        r"🔺上車|⬆️|🔺)\s*[:：●]?\s*"
    )
    dropoff_label = (
        r"^(第一個下車點|第二個下車點|第三個下車點|第二下車|第三下車|"
        r"下車地址|下車地點|下車地|下車|到達|終點|目的地|目的●|目的|下|"
        r"🔻下車|🔽|🔻)\s*[:：●]?\s*"
    )
    continuation_label = r"^(?:\(加?\d+\)|（加?\d+）|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、])\s*"

    current_mode = None

    for line in lines:
        if re.match(pickup_label, line):
            current_mode = "pickup"
            addr = re.sub(pickup_label, "", line).strip()
            addr = re.sub(r"^[：:●]+\s*", "", addr)
            if addr:
                cleaned = clean_address(addr)
                if cleaned:
                    pickups.append(cleaned)
            continue

        if re.match(dropoff_label, line):
            current_mode = "dropoff"
            addr = re.sub(dropoff_label, "", line).strip()
            addr = re.sub(r"^[：:●]+\s*", "", addr)
            if addr:
                addr = re.sub(continuation_label, "", addr).strip()
                cleaned = clean_address(addr)
                if cleaned:
                    dropoffs.append(cleaned)
            continue

        if stop_keywords.match(line):
            current_mode = None
            continue

        if re.match(continuation_label, line):
            addr = re.sub(continuation_label, "", line).strip()
            cleaned = clean_address(addr)
            if cleaned:
                if current_mode == "pickup":
                    pickups.append(cleaned)
                else:
                    dropoffs.append(cleaned)
                    current_mode = "dropoff"
            continue

        if current_mode in ("pickup", "dropoff"):
            if re.search(
                r"(市|區|鄉|鎮|路|街|巷|弄|號|機場|航廈|桃機|T1|T2|錢櫃|車站)",
                line
            ):
                cleaned = clean_address(line)
                if cleaned:
                    if current_mode == "pickup":
                        pickups.append(cleaned)
                    else:
                        dropoffs.append(cleaned)
            continue

    if not pickups and not dropoffs:
        address_like = []
        for line in lines:
            if re.search(
                r"(市|區|鄉|鎮|路|街|巷|弄|號|機場|航廈|桃機|T1|T2|錢櫃|車站)",
                line
            ):
                cleaned = clean_address(clean_line(line))
                if cleaned:
                    address_like.append(cleaned)

        if len(address_like) == 1:
            pickups.append(address_like[0])
        elif len(address_like) >= 2:
            pickups.append(address_like[0])
            dropoffs.extend(address_like[1:])

    return pickups, dropoffs


def format_booking(text):
    date_text = parse_date(text)
    time_text = parse_time(text)
    price_text = parse_price(text)
    note_text = parse_notes(text)
    service_type, flight_text = parse_airport_info(text)
    pickups, dropoffs = parse_addresses(text)

    airport_booking = is_airport_booking(text, service_type, pickups, dropoffs)
    people_count = parse_people_count(text)
    luggage_text = parse_luggage(text)

    output = []

    first_line_parts = [x for x in [date_text, time_text, service_type, flight_text] if x]
    if first_line_parts:
        output.append(" ".join(first_line_parts))

    for p in pickups:
        output.append(f"⬆️{p}")

    if dropoffs:
        output.append(f"下車地點：{dropoffs[0]}")
        for d in dropoffs[1:]:
            output.append(f"🔽{d}")

    info_parts = []

    if airport_booking:
        if people_count > 0:
            info_parts.append(f"{people_count}人")
        if luggage_text:
            info_parts.append(luggage_text)
    else:
        if people_count > 4:
            extra = (people_count - 4) * 100
            info_parts.append(f"{people_count}人 +{extra}")

    if note_text:
        info_parts.append(note_text)

    if info_parts:
        output.append("｜".join(info_parts))

    if price_text:
        output.append(price_text)

    return "\n".join(output).strip()

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


notify_startup()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))