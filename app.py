import os
import re
import logging
from datetime import datetime
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# =====================================================
# 基本設定
# =====================================================
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# =====================================================
# 關鍵字設定
# =====================================================
NOW_WORDS = ["現在", "立即", "馬上", "立刻", "即時"]
TODAY_WORDS = ["今天", "今日", "當日"] + NOW_WORDS

UP_LABELS = ["上車地址", "上車地點", "上車", "第一上車", "第二上車", "第三上車"]
DOWN_LABELS = ["下車地址", "下車地點", "下車", "第一下車", "第二下車", "第三下車"]

NOTE_KEYWORDS = [
    "禁煙", "禁菸", "慢慢開", "進口", "有寵", "有寵物", "寵物",
    "休旅", "轉帳", "禁快車", "安全座椅", "兒童座椅", "舉牌",
]

# =====================================================
# Flask / LINE Webhook
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return "OK"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    app.logger.info("Request body: %s", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        app.logger.exception("Webhook error: %s", e)
        abort(500)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text or ""

    # 防止群組一般聊天也觸發，例如：好、要嗎、謝謝
    if not should_process(text):
        return

    result = format_booking(text)
    if result:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=result)
        )

# =====================================================
# 是否需要處理
# =====================================================
def should_process(text: str) -> bool:
    t = normalize_text(text)

    if len(t.strip()) <= 2:
        return False

    strong_keywords = [
        "上車", "下車", "日期", "時間", "人數", "乘坐人數", "手機", "電話",
        "行李", "航班", "備註", "機場", "桃機", "松機", "航廈", "地址",
        "💰", "$", "＄"
    ]

    if any(k in t for k in strong_keywords):
        return True

    # 無標籤但有兩行以上像地址，也處理：第一行上車、第二行下車
    address_like_lines = []
    for line in split_lines(t):
        if is_address_like(line):
            address_like_lines.append(line)

    return len(address_like_lines) >= 2

# =====================================================
# 主格式化
# =====================================================
def format_booking(text: str) -> str:
    original_text = text
    text = normalize_text(text)
    lines = split_lines(text)

    date_text = parse_date(text)
    time_text = parse_time(text)
    price_text = parse_price(text)
    people_line = parse_people(text)
    note_line = parse_notes(text)

    ups, downs = parse_addresses(lines)

    output = []

    # 日期時間：今天/當日不顯示日期，但時間仍要顯示
    date_time_parts = []
    if date_text:
        date_time_parts.append(date_text)
    if time_text:
        date_time_parts.append(time_text)
    if date_time_parts:
        output.append(" ".join(date_time_parts))

    for addr in ups:
        output.append(f"⬆️：{addr}")

    if downs:
        output.append(f"下車地點：{downs[0]}")
        for addr in downs[1:]:
            output.append(f"🔽{addr}")

    people_note = ""
    if people_line:
        people_note += people_line
    if note_line:
        if people_note:
            people_note += "｜" + note_line
        else:
            people_note += "｜" + note_line
    if people_note:
        output.append(people_note)

    if price_text:
        output.append(price_text)

    return "\n".join(output).strip()

# =====================================================
# 基本文字處理
# =====================================================
def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("臺", "台")
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("；", ";")
    return text


def split_lines(text: str):
    result = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if set(line) <= set("-—_─═ "):
            continue
        if "悠遊GO" in line or "機場預約" in line:
            continue
        result.append(line)
    return result

# =====================================================
# 日期處理
# =====================================================
def parse_date(text: str) -> str:
    today = datetime.now()

    # 今天、今日、當日、現在：不顯示日期
    if re.search(r"日期[:：\s]*(今天|今日|當日|現在|立即|馬上|立刻)", text):
        return ""

    # 日期：6/24（三） 或 6/24
    m = re.search(r"日期[:：\s]*([0-9]{1,2})\s*/\s*([0-9]{1,2})", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        # 如果是今天，不顯示日期
        if month == today.month and day == today.day:
            return ""
        return f"{month}/{day}"

    # 獨立日期：7/14（三）
    m = re.search(r"(?:^|\n)\s*([0-9]{1,2})\s*/\s*([0-9]{1,2})(?:\s*\([^)]*\))?", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if month == today.month and day == today.day:
            return ""
        return f"{month}/{day}"

    # 日期：24、日期：24號，視為當月
    m = re.search(r"日期[:：\s]*([0-9]{1,2})\s*號?", text)
    if m:
        day = int(m.group(1))
        if day == today.day:
            return ""
        return f"{today.month}/{day}"

    return ""

# =====================================================
# 時間處理
# =====================================================
def parse_time(text: str) -> str:
    # 現在/立即/馬上/立刻：不顯示時間
    if re.search(r"時間[:：\s]*(現在|立即|馬上|立刻|即時)", text):
        return ""

    candidates = []

    # 時間：早上5:30、時間：下午 6:30、早上5:30
    pattern1 = re.compile(
        r"(?:時間[:：\s]*)?(早上|上午|下午|晚上|中午|凌晨)?\s*([0-9]{1,2})\s*[:：]\s*([0-9]{2})\s*(am|pm|AM|PM)?"
    )
    for m in pattern1.finditer(text):
        candidates.append((m.group(1) or "", m.group(2), m.group(3), m.group(4) or ""))

    # 時間：0600pm、0600 pm、6pm、0500
    pattern2 = re.compile(
        r"(?:時間[:：\s]*)?(早上|上午|下午|晚上|中午|凌晨)?\s*([0-9]{1,4})\s*(am|pm|AM|PM)?"
    )
    for m in pattern2.finditer(text):
        raw = m.group(2)
        period = m.group(1) or ""
        ampm = m.group(3) or ""

        # 避免把日期、價格、地址號碼誤當時間
        start = max(0, m.start() - 6)
        prefix = text[start:m.start()]
        full = m.group(0)
        if "/" in full or "$" in prefix or "💰" in prefix:
            continue
        if len(raw) <= 2 and not period and not ampm and "時間" not in full:
            continue

        if len(raw) in [3, 4]:
            hour = raw[:-2]
            minute = raw[-2:]
            candidates.append((period, hour, minute, ampm))
        elif len(raw) <= 2 and (period or ampm or "時間" in full):
            candidates.append((period, raw, "00", ampm))

    if not candidates:
        return ""

    period, hour_s, minute_s, ampm = candidates[0]

    try:
        hour = int(hour_s)
        minute = int(minute_s)
    except ValueError:
        return ""

    ampm = ampm.lower()

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif period in ["下午", "晚上"] and hour < 12:
        hour += 12
    elif period == "中午" and hour < 12:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return ""

    return f"{hour:02d}:{minute:02d}"

# =====================================================
# 金額處理
# =====================================================
def parse_price(text: str) -> str:
    # 支援 💰1900、固定💰1900、$900、＄900
    matches = re.findall(r"(?:固定\s*)?(?:💰|[$＄])\s*([0-9,]+)", text)
    if not matches:
        return ""
    amount = matches[-1].replace(",", "")
    return f"💰{amount}"

# =====================================================
# 人數處理
# =====================================================
def parse_people(text: str) -> str:
    # 支援 人數：5、乘坐人數：5、5人
    total = None

    m = re.search(r"(?:乘坐人數|人數)[:：\s]*([0-9]+)", text)
    if m:
        total = int(m.group(1))
    else:
        m = re.search(r"([0-9]+)\s*人", text)
        if m:
            total = int(m.group(1))

    # 支援 2大2小，總數 4
    m = re.search(r"(?:乘坐人數|人數)[:：\s]*([0-9]+)\s*大\s*([0-9]+)\s*小", text)
    if m:
        total = int(m.group(1)) + int(m.group(2))

    if total is None:
        return ""

    if total > 4:
        extra = (total - 4) * 100
        return f"{total}人 +{extra}"

    # 4人以下不顯示
    return ""

# =====================================================
# 備註處理
# =====================================================
def parse_notes(text: str) -> str:
    notes = []

    m = re.search(r"備註[:：\s]*(.*)", text)
    if m:
        raw = m.group(1).strip()
        raw = raw.replace("，", " ").replace(",", " ").replace("、", " ")
        for part in raw.split():
            clean = part.strip()
            if clean and not looks_like_address_tail(clean):
                notes.append(clean)

    for keyword in NOTE_KEYWORDS:
        if keyword in text and keyword not in notes:
            notes.append(keyword)

    if not notes:
        return ""

    return "".join(f"✅{n}" for n in notes)

# =====================================================
# 地址處理
# =====================================================
def parse_addresses(lines):
    ups = []
    downs = []

    for line in lines:
        clean_line = line.strip()

        # 跳過非地址欄位
        if re.match(r"^(日期|時間|人數|乘坐人數|手機|電話|行李|航班|航班編號|備註)[:：]", clean_line):
            continue
        if re.search(r"(?:💰|[$＄])\s*\d+", clean_line):
            continue

        addr_type = None
        addr = ""

        # 上車
        m = re.match(r"^(?:第?[一二三123]?[\s]*上車(?:地址|地點)?|上車(?:地址|地點)?|上車)\s*[:：]?\s*(.+)$", clean_line)
        if m:
            addr_type = "up"
            addr = m.group(1)

        # 下車
        if addr_type is None:
            m = re.match(r"^(?:第?[一二三123]?[\s]*下車(?:地址|地點)?|下車(?:地址|地點)?|下車)\s*[:：]?\s*(.+)$", clean_line)
            if m:
                addr_type = "down"
                addr = m.group(1)

        if addr_type and addr:
            simplified = simplify_address(addr)
            if simplified:
                if addr_type == "up":
                    ups.append(simplified)
                else:
                    downs.append(simplified)

    # 無標籤雙地址：第一行上車、第二行下車
    if not ups and not downs:
        address_like = []
        for line in lines:
            if is_address_like(line):
                address_like.append(simplify_address(line))
        if len(address_like) >= 2:
            ups.append(address_like[0])
            downs.append(address_like[1])

    return ups, downs


def simplify_address(addr: str) -> str:
    addr = addr.strip()
    addr = re.sub(r"^[0-9]{3,5}\s*", "", addr)  # 郵遞區號
    addr = re.sub(r"^(地址|上車地址|下車地址|上車|下車)\s*[:：]?\s*", "", addr)
    addr = addr.replace("臺", "台")
    addr = re.sub(r"\s+", "", addr)

    # 移除 XX里，例如：幸福里、中山里
    addr = re.sub(r"[^縣市區鄉鎮路街巷弄號]{1,6}里", "", addr)

    # 地標不硬切
    if not is_address_like(addr):
        return addr

    # 台北/新北/桃園/北市：移除城市名，保留區後面
    addr = re.sub(r"^(台北市|北市|新北市|桃園市)", "", addr)

    # 如果地址內還有區，從區名前一段開始保留
    m = re.search(r"([\u4e00-\u9fff]{1,4}區.+)", addr)
    if m:
        addr = m.group(1)

    return addr


def is_address_like(s: str) -> bool:
    s = s.strip()
    if not s:
        return False

    # 地標也算目的地，但不要讓單純文字「好」通過
    landmark_words = ["機場", "桃機", "松機", "航廈", "T1", "T2", "台北101", "台北市政府"]
    if any(k in s for k in landmark_words):
        return True

    address_tokens = ["縣", "市", "區", "鄉", "鎮", "路", "街", "巷", "弄", "號", "大道"]
    return any(k in s for k in address_tokens) and bool(re.search(r"\d", s))


def looks_like_address_tail(s: str) -> bool:
    return bool(re.search(r"(路|街|巷|弄|號|樓|區)", s))

# =====================================================
# 啟動
# =====================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
