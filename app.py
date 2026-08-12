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

BOT_VERSION = "v3.0.7"
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
        "⬆️", "🔽", "🔺", "🔻", "出發", "起點", "到達", "終點",
        "目的", "目的地", "目的●", "日期", "叫車日期", "時間", "預約",
        "人數", "乘坐人數", "乘車人數", "機場", "桃機", "航廈",
        "接機", "送機", "航班", "行李", "💰", "$", "＄", "固定"
    ]
    if any(k in text for k in keywords):
        return True

    if re.search(r"(?m)^\s*(上|下|起)\s*[:： ]", text):
        return True

    if re.search(r"(?m)^\s*\d{1,2}[／/-]\d{1,2}\s+\d{1,2}[:：]\d{2}", text):
        return True

    if re.search(r"(?m)^\s*\d{1,2}[:：]\d{2}\s*$", text):
        return True

    return False


def clean_line(line):
    line = line.strip()
    line = re.sub(r"^[\s\-—–_]+", "", line)
    line = re.sub(
        r"^(叫車日期|日期|時間|上車時間|第一個上車點|第二個上車點|第三個上車點|"
        r"第一個下車點|第二個下車點|第三個下車點|第二上車|第三上車|第二下車|第三下車|"
        r"上車地址|下車地址|上車地點|下車地點|上車地|下車地|上車|下車|"
        r"出發|起點|到達|終點|目的地|目的●|目的|上|下|起|地址|"
        r"🔺上車|🔻下車|⬆️|🔽|🔺|🔻)\s*[:：●]?\s*",
        "",
        line
    )
    return line.strip()


def looks_like_address(value):
    value = value.strip()
    if not value:
        return False

    if re.search(r"(路|街|巷|弄|號|區|鄉|鎮|市|村|里|機場|航廈|桃機|車站|錢櫃|飯店|酒店|大樓)", value):
        return True

    # 常見地標：信義一蘭拉麵、士林、板橋等
    if re.search(r"(拉麵|餐廳|KTV|百貨|醫院|學校|夜市|捷運|高鐵|火車站)", value, re.I):
        return True

    short_places = [
        "士林", "信義", "板橋", "新莊", "三重", "中和", "永和", "土城",
        "樹林", "汐止", "新店", "淡水", "內湖", "南港", "北投", "萬華"
    ]
    return value in short_places


def clean_address(addr):
    addr = addr.strip()
    addr = re.sub(r"^[：:●\s]+", "", addr)

    # 多點編號：1桃園區...、2士林、(加1)...、①...
    addr = re.sub(
        r"^(?:\(加?\d+\)|（加?\d+）|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、]|\d+(?=[\u4e00-\u9fff]))\s*",
        "",
        addr
    )

    # 郵遞區號 3~6 碼
    addr = re.sub(r"^\d{3,6}(?=[\u4e00-\u9fff])", "", addr)

    # 國名與常見縣市前綴
    addr = re.sub(r"^(台灣|臺灣)", "", addr)
    addr = re.sub(r"^(台北市|臺北市|新北市|桃園市|北市)", "", addr)
    addr = re.sub(r"^(台北|臺北|新北)(?=[\u4e00-\u9fff]{1,4}區)", "", addr)

    # 移除行政區後面的里名：中山區西門里... -> 中山區...
    addr = re.sub(r"(?<=[區鄉鎮市])[\u4e00-\u9fff]{1,8}里", "", addr)

    # 航廈格式
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
        "中山", "松山", "大同", "萬華", "信義", "內湖", "南港", "士林",
        "北投", "文山", "中正", "大安", "板橋", "新莊", "三重", "中和",
        "永和", "土城", "樹林", "汐止", "蘆洲", "泰山", "林口", "淡水",
        "新店", "五股", "深坑", "三峽", "鶯歌", "瑞芳", "金山", "萬里",
        "中壢", "平鎮", "八德", "龜山", "蘆竹", "大溪", "楊梅", "龍潭",
        "大園", "觀音", "新屋"
    ]
    for district in sorted(districts, key=len, reverse=True):
        if re.match(rf"^{district}(?!區)", addr):
            # 裸地名如「士林」保持原樣；地標名稱如「信義一蘭拉麵」也不強制補區
            if addr != district and not re.search(r"(拉麵|餐廳|KTV|百貨|醫院|學校|夜市|捷運)", addr):
                addr = district + "區" + addr[len(district):]
            break

    addr = re.sub(r"\s+", "", addr)
    return addr.strip()


def parse_date(text):
    today = datetime.now(ZoneInfo("Asia/Taipei"))
    current_month = today.month
    current_day = today.day

    date_label = r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    if re.search(
        rf"{date_label}\s*[:：]?\s*(當日免填|今日免填|今天|今日|現在|立即|馬上|立刻)",
        text
    ):
        return ""

    m = re.search(
        rf"{date_label}\s*[:：]?\s*(\d{{4}})[／/-](\d{{1,2}})[／/-](\d{{1,2}})",
        text
    )
    if m:
        month, day = int(m.group(2)), int(m.group(3))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    m = re.search(
        rf"{date_label}\s*[:：]?\s*(\d{{1,2}})[／/-](\d{{1,2}})",
        text
    )
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if month == current_month and day == current_day:
            return ""
        return f"{month}/{day}"

    m = re.search(rf"{date_label}\s*[:：]?\s*(\d{{1,2}})\s*(?:號|日)?", text)
    if m:
        day = int(m.group(1))
        if day == current_day:
            return ""
        return f"{current_month}/{day}"

    # 極簡：8/26 03:30 TG637 送機、8/9 2200
    m = re.search(r"(?m)^\s*(\d{1,2})[／/-](\d{1,2})(?=\s+(?:\d{1,2}[:：]\d{2}|\d{4})\b)", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
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



def should_hide_booking_time(text, hour, minute):
    """
    預約時間距離台北當下時間 10 分鐘內（含）時不顯示。
    有明確日期時使用該日期；無日期／當日免填時，以最近的合理時刻判斷。
    """
    from datetime import timedelta

    now = datetime.now(ZoneInfo("Asia/Taipei"))
    target_date = now.date()
    explicit_date = False

    m = re.search(
        r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?"
        r"\s*[:：]?\s*(\d{4})[／/-](\d{1,2})[／/-](\d{1,2})",
        text
    )
    if m:
        try:
            target_date = datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3))
            ).date()
            explicit_date = True
        except ValueError:
            pass
    else:
        m = re.search(
            r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?"
            r"\s*[:：]?\s*(\d{1,2})[／/-](\d{1,2})",
            text
        )
        if not m:
            m = re.search(
                r"(?m)^\s*(\d{1,2})[／/-](\d{1,2})"
                r"(?=\s+(?:\d{1,2}[:：]\d{2}|\d{4})\b)",
                text
            )

        if m:
            month, day = int(m.group(1)), int(m.group(2))
            try:
                year = now.year
                if now.month == 12 and month == 1:
                    year += 1
                elif now.month == 1 and month == 12:
                    year -= 1
                target_date = datetime(year, month, day).date()
                explicit_date = True
            except ValueError:
                pass

    target = datetime(
        target_date.year, target_date.month, target_date.day,
        hour, minute, tzinfo=ZoneInfo("Asia/Taipei")
    )

    if not explicit_date and target < now:
        target += timedelta(days=1)

    diff_minutes = (target - now).total_seconds() / 60
    return 0 <= diff_minutes <= 10


def format_booking_time(text, hour, minute):
    if should_hide_booking_time(text, hour, minute):
        return ""
    return f"{hour:02d}:{minute:02d}"


def format_booking_time_string(text, value):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value or "")
    if not m:
        return value
    return format_booking_time(text, int(m.group(1)), int(m.group(2)))


def nearest_ambiguous_hour(hour):
    """未寫上午/下午時，選擇現在之後最近的同一個 12 小時制時刻。"""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    candidates = []

    if hour == 12:
        hours = [0, 12]
    elif 1 <= hour <= 11:
        hours = [hour, hour + 12]
    else:
        return hour

    for h in hours:
        candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate <= now:
            from datetime import timedelta
            candidate += timedelta(days=1)
        candidates.append(candidate)

    return min(candidates).hour


def parse_time(text):
    time_label = r"(?:時間|上車時間)(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    # 空白或現在/即時免填
    if re.search(
        rf"{time_label}\s*[:：]?\s*(?:現在|即時免填|現在免填|立即|馬上|立刻|24H|24h|全天|全天候)?\s*$",
        text,
        re.MULTILINE
    ):
        return ""

    # 上車時間欄若其實填地址，不當時間處理
    m = re.search(r"(?m)^上車時間\s*[:：]?\s*(.+)$", text)
    if m and looks_like_address(m.group(1)):
        pass

    # 預約1:05
    m = re.search(r"預約\s*[:：]?\s*(\d{1,2})\s*[:：]\s*(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_booking_time(text, hour, minute)

    # 等等3. / 等等3點 / 等3點
    m = re.search(
        rf"{time_label}\s*[:：]?\s*(?:等等?|待會(?:兒)?)\s*(\d{{1,2}})\s*(?:點|[.。])?\s*$",
        text,
        re.MULTILINE
    )
    if m:
        raw_hour = int(m.group(1))
        if 1 <= raw_hour <= 12:
            return format_booking_time(text, nearest_ambiguous_hour(raw_hour), 0)
        if 13 <= raw_hour <= 23:
            return format_booking_time(text, raw_hour, 0)

    # 08:35pm
    m = re.search(
        rf"{time_label}\s*[:：]?\s*(\d{{1,2}})\s*[:：]\s*(\d{{2}})\s*(am|pm)",
        text, re.I
    )
    if m:
        hour, minute, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        return format_booking_time(text, hour, minute)

    # 下午6:30
    m = re.search(
        rf"{time_label}\s*[:：]?\s*(早上|上午|下午|晚上|中午|凌晨)?\s*(\d{{1,2}})\s*[:：]\s*(\d{{2}})",
        text, re.I
    )
    if m:
        return format_booking_time_string(text, convert_time(m.group(1) or "", int(m.group(2)), int(m.group(3))))

    # 下午3點 / 3點
    m = re.search(
        rf"{time_label}\s*[:：]?\s*(早上|上午|下午|晚上|中午|凌晨)?\s*(\d{{1,2}})\s*點",
        text, re.I
    )
    if m:
        period, hour = m.group(1) or "", int(m.group(2))
        if not period and 1 <= hour <= 12:
            hour = nearest_ambiguous_hour(hour)
        return format_booking_time_string(text, convert_time(period, hour, 0))

    # 0600pm
    m = re.search(rf"{time_label}\s*[:：]?\s*(\d{{1,2}})(\d{{2}})\s*(am|pm)", text, re.I)
    if m:
        hour, minute, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        return format_booking_time(text, hour, minute)

    # 0500 / 1830
    m = re.search(rf"{time_label}\s*[:：]?\s*(\d{{1,2}})(\d{{2}})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_booking_time(text, hour, minute)

    # 極簡：8/26 03:30 ...
    m = re.search(r"(?m)^\s*\d{1,2}[／/-]\d{1,2}\s+(\d{1,2})[:：](\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_booking_time(text, hour, minute)

    # 極簡：8/9 2200
    m = re.search(r"(?m)^\s*\d{1,2}[／/-]\d{1,2}\s+(\d{2})(\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_booking_time(text, hour, minute)

    # 單獨一行 04:30
    m = re.search(r"(?m)^\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*$", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_booking_time(text, hour, minute)

    return ""


def parse_price(text):
    patterns = [
        r"固定\s*💰?\s*(\d+)",
        r"💰\s*(\d+)",
        r"[$＄]\s*(\d+)",
        r"(?m)^\s*(\d{3,5})\s*元\s*$"
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return f"💰{m.group(1)}"
    return ""


def chinese_num_to_int(s):
    mapping = {
        "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10
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
        r"(?m)^(?:人數|乘坐人數|乘車人數)\s*[:：]?\s*([0-9一二兩三四五六七八九十]+)\s*(?:人)?",
        text
    )
    if m:
        people = chinese_num_to_int(m.group(1))
        return people if 0 < people <= 20 else 0

    # 2人2行李 / 一般 3人
    m = re.search(r"([0-9一二兩三四五六七八九十]+)\s*人", text)
    if m:
        people = chinese_num_to_int(m.group(1))
        return people if 0 < people <= 20 else 0

    # 備註：三個人
    m = re.search(
        r"(?m)^(?:備註|備注|其他備註|其他備注)\s*[:：]?\s*.*?"
        r"([0-9一二兩三四五六七八九十]+)\s*(?:個)?人",
        text
    )
    if m:
        people = chinese_num_to_int(m.group(1))
        return people if 0 < people <= 20 else 0

    return 0


def parse_people(text):
    people = parse_people_count(text)
    if people > 4:
        return f"{people}人 +{(people - 4) * 100}"
    return ""


def parse_luggage(text):
    # 行李數量：3 / 行李箱：2
    m = re.search(
        r"(?m)^(?:行李數量|行李數|行李箱)\s*[:：]?\s*(\d+)\s*(?:個|件|箱)?\s*$",
        text
    )
    if m:
        count = int(m.group(1))
        return f"🧳{count}件" if count > 0 else ""

    # 2人2行李
    m = re.search(r"\d+\s*人\s*(\d+)\s*(?:個|件|箱)?\s*行李", text)
    if m:
        count = int(m.group(1))
        return f"🧳{count}件" if count > 0 else ""

    # 3個29吋行李
    m = re.search(r"(\d+)\s*(?:個|件|箱)\s*\d{2}\s*吋\s*行李", text)
    if m:
        return f"🧳{int(m.group(1))}件"

    # 29吋3件 / 27吋1件29吋2件
    size_items = re.findall(r"\d{2}\s*吋\s*(\d+)\s*(?:個|件|箱)?", text)
    if size_items:
        return f"🧳{sum(int(x) for x in size_items)}件"

    # 備註內 3個行李
    m = re.search(r"(\d+)\s*(?:個|件|箱)\s*行李", text)
    if m:
        return f"🧳{int(m.group(1))}件"

    return ""


def parse_notes(text):
    ignore_notes = {
        "0", "無", "沒有", "無備註", "無備注", "無行李", "沒行李",
        "免備註", "免備注", "不用", "正常", "一般", "皆可",
        "N", "n", "NO", "No", "no", "-", "--", "免"
    }

    for line in text.splitlines():
        if re.match(r"^\s*(備註|備注|其他備註|其他備注)\s*[:：]?", line):
            note = re.sub(
                r"^\s*(備註|備注|其他備註|其他備注)\s*[:：]?\s*",
                "", line
            ).strip()

            if not note or note in ignore_notes:
                return ""

            note = re.sub(r"(^|[\s，,、/]+)(接機|送機)(?=$|[\s，,、/]+)", " ", note)
            note = re.sub(r"([0-9一二兩三四五六七八九十]+)\s*(?:個)?人", " ", note)
            note = re.sub(r"\d+\s*(?:個|件|箱)\s*(?:\d{2}\s*吋)?\s*行李", " ", note)
            note = re.sub(r"\d{2}\s*吋\s*\d+\s*(?:個|件|箱)?(?:行李)?", " ", note)

            if re.search(r"^(?:💰|[$＄]|固定)\s*\d+", note.strip()):
                return ""

            note = re.sub(r"[，,、/]+", " ", note)
            parts = [p.strip() for p in note.split() if p.strip() and p.strip() not in ignore_notes]
            if not parts:
                return ""
            return "".join(f"✅{p}" for p in parts)

    return ""


def parse_airport_info(text):
    service_type = ""

    # 正式欄位
    m = re.search(
        r"(?:接機\s*[／/]\s*送機|接機送機)\s*[:：]?\s*(接機|送機)",
        text
    )
    if m:
        service_type = m.group(1)
    else:
        # 極簡單、備註
        m = re.search(r"(?<![／/])(接機|送機)", text)
        if m:
            service_type = m.group(1)

    flight = ""
    m = re.search(
        r"(?:航班|航班編號|航班號碼)\s*[:：]?[^\n]*?"
        r"\b([A-Za-z0-9]{2,3}\s*\d{2,4})\b",
        text, re.I
    )
    if m:
        flight = re.sub(r"\s+", "", m.group(1)).upper()
    else:
        # 極簡機場格式：8/26 03:30 TG637 送機
        if re.search(r"(接機|送機|機場|航廈|桃機)", text):
            m = re.search(
                r"(?<![A-Za-z0-9])((?:[A-Za-z]{1,3}\d{2,4}|\d[A-Za-z]\d{2,4}))(?![A-Za-z0-9])",
                text,
                re.I
            )
            if m:
                flight = m.group(1).upper()

    return service_type, flight


def is_airport_booking(text, service_type, pickups, dropoffs):
    if service_type in ["接機", "送機"]:
        return True
    combined = "\n".join(pickups + dropoffs) + "\n" + text
    return bool(re.search(r"(桃園(?:國際)?機場|桃機|第一航廈|第二航廈|\bT1\b|\bT2\b|機場)", combined, re.I))


def parse_addresses(text):
    pickups = []
    dropoffs = []
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]

    pickup_label = (
        r"^(第一個上車點|第二個上車點|第三個上車點|第二上車|第三上車|"
        r"上車地址|上車地點|上車地|上車|出發|起點|起|上|🔺上車|⬆️|🔺)\s*[:：●]?\s*"
    )
    dropoff_label = (
        r"^(第一個下車點|第二個下車點|第三個下車點|第二下車|第三下車|"
        r"下車地址|下車地點|下車地|下車|到達|終點|目的地|目的●|目的|下|"
        r"🔻下車|🔽|🔻)\s*[:：●]?\s*"
    )
    continuation_label = (
        r"^(?:\(加?\d+\)|（加?\d+）|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、]|"
        r"\d+(?=[\u4e00-\u9fff]))\s*"
    )
    stop_keywords = re.compile(
        r"^(?:叫車日期|日期|時間|人數|乘坐人數|乘車人數|手機號碼|連絡電話|聯絡電話|電話|TEL|"
        r"行李數量|行李數|行李箱|航班|接機／送機|接機/送機|備註|備注|其他備註|其他備注|"
        r"固定|💰|[$＄]|Line匿稱|Line暱稱)\s*(?:\([^)]*\)|（[^）]*）)?\s*[:：]?",
        re.I
    )

    current_mode = None
    i = 0

    while i < len(raw_lines):
        line = raw_lines[i]

        # 固定表單提示文字，不當地址或備註處理
        if re.search(r"^(麻煩填寫完整地址|麻煩提供正確電話)", line):
            i += 1
            continue

        # 特殊：上車時間欄誤填地址
        m = re.match(r"^上車時間\s*[:：]?\s*(.+)$", line)
        if m and looks_like_address(m.group(1)):
            value = m.group(1).strip()

            # 若地址在「里」前被換行，例如 景安 / 里景平路...
            if i + 1 < len(raw_lines) and re.match(r"^里", raw_lines[i + 1]):
                value += raw_lines[i + 1]
                i += 1

            cleaned = clean_address(value)
            if cleaned:
                pickups.append(cleaned)
            current_mode = "pickup"
            i += 1
            continue

        if re.match(pickup_label, line):
            current_mode = "pickup"
            value = re.sub(pickup_label, "", line).strip()

            if value and i + 1 < len(raw_lines) and re.match(r"^里", raw_lines[i + 1]):
                value += raw_lines[i + 1]
                i += 1

            if value:
                cleaned = clean_address(value)
                if cleaned:
                    pickups.append(cleaned)
            i += 1
            continue

        if re.match(dropoff_label, line):
            current_mode = "dropoff"
            value = re.sub(dropoff_label, "", line).strip()
            if value:
                cleaned = clean_address(value)
                if cleaned:
                    dropoffs.append(cleaned)
            i += 1
            continue

        if stop_keywords.match(line):
            current_mode = None
            i += 1
            continue

        # 下車地址後的 2士林 / 1桃園區...
        if current_mode in ("pickup", "dropoff") and re.match(continuation_label, line):
            value = re.sub(continuation_label, "", line).strip()
            cleaned = clean_address(value)
            if cleaned:
                if current_mode == "pickup":
                    pickups.append(cleaned)
                else:
                    dropoffs.append(cleaned)
                    current_mode = "dropoff"
            i += 1
            continue

        # 上一個地址被換行切在里之前
        if current_mode in ("pickup", "dropoff") and re.match(r"^里", line):
            target = pickups if current_mode == "pickup" else dropoffs
            if target:
                # 已清理過的上一段不含里名，直接把里後面的街路接上
                tail = re.sub(r"^里", "", line)
                target[-1] = clean_address(target[-1] + tail)
            i += 1
            continue

        if current_mode in ("pickup", "dropoff") and looks_like_address(line):
            cleaned = clean_address(line)
            if cleaned:
                if current_mode == "pickup":
                    pickups.append(cleaned)
                else:
                    dropoffs.append(cleaned)
            i += 1
            continue

        i += 1

    # 完全沒有標籤時，依出現順序：第一個上車，其餘下車
    if not pickups and not dropoffs:
        candidates = []
        for line in raw_lines:
            # 排除日期時間、人數、價格、航班等
            if re.search(r"^\s*\d{1,2}[／/-]\d{1,2}\s+\d{1,2}[:：]\d{2}", line):
                continue
            if re.search(r"^\s*\d+\s*人", line):
                continue
            if re.search(r"^\s*💰?\d+\s*元?\s*$", line):
                continue
            if looks_like_address(line):
                cleaned = clean_address(clean_line(line))
                if cleaned:
                    candidates.append(cleaned)

        if len(candidates) == 1:
            pickups.append(candidates[0])
        elif len(candidates) >= 2:
            pickups.append(candidates[0])
            dropoffs.extend(candidates[1:])

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
            info_parts.append(f"{people_count}人 +{(people_count - 4) * 100}")

    if note_text:
        info_parts.append(note_text)

    if info_parts:
        output.append("｜".join(info_parts))

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


notify_startup()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))