import os
import re
from functools import lru_cache
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

BOT_VERSION = "v3.4.1"
GROUP_ID = "C68622c8e7215bffc165b1f657c148b4e"


def notify_startup():
    """
    同一個 Render 容器、同一版本只送一次啟動通知。
    Gunicorn worker 重載/多 worker import 不再重複通知。
    新部署/新容器仍會正常通知。
    """
    sentinel = f"/tmp/line_bot_startup_{BOT_VERSION}.lock"

    try:
        fd = os.open(
            sentinel,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600
        )
        os.close(fd)
    except FileExistsError:
        return
    except Exception as e:
        # Sentinel 建立失敗時，不因通知功能影響 Bot 本體。
        print("Startup sentinel error:", e)
        return

    try:
        now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
        line_bot_api.push_message(
            GROUP_ID,
            TextSendMessage(
                text=f"系統已啟動 ✅\nCC專屬助理已上線 ✅\n有任何問題請洽CC北鼻✅\n版本：{BOT_VERSION}\n時間：{now}"
            )
        )
    except Exception as e:
        # 若通知真的失敗，移除 sentinel，下一次 worker 啟動可再嘗試。
        try:
            os.remove(sentinel)
        except OSError:
            pass
        print("Startup notify error:", e)





# ============================================================
# v3.1.0 Parser
# 流程：正規化 → 欄位解析 → 地址合併/清理 → 商業規則 → 固定輸出
# ============================================================

NOISE_PATTERNS = [
    r"^麻煩填寫完整地址",
    r"^麻煩提供正確電話",
    r"^💟?精采派車預約💟?$",
    r"^✠.*新多元服務.*✠$",
    r"^[—\-_=]{3,}$",
]

PHONE_LABELS = (
    "手機", "手機號碼", "電話", "TEL", "Tel", "tel",
    "連絡電話", "聯絡電話"
)

NOTE_LABELS = ("其他備註", "其他備注", "備註", "備注")

PICKUP_LABELS = (
    "第一個上車點", "第二個上車點", "第三個上車點",
    "第二上車", "第三上車",
    "上車地址", "上車地點", "上車地", "上車",
    "⬆️位置", "⬆位置", "出發地", "出發", "起點", "起",
    "🔺上車", "⬆️", "⬆", "🔺", "上"
)

DROPOFF_LABELS = (
    "第一個下車點", "第二個下車點", "第三個下車點",
    "第二下車", "第三下車",
    "下車地址", "下車地點", "下車地", "下車",
    "到達", "終點", "目的地", "目地", "目的●", "目的",
    "🔻下車", "🔽", "🔻", "下"
)

FIELD_PREFIXES = (
    "叫車日期", "日期", "時間", "上車時間",
    "人數", "乘坐人數", "乘車人數",
    "行李數量", "行李數", "行李箱",
    "航班", "航班編號", "航班號碼",
    "接機／送機", "接機/送機",
    "Line匿稱", "Line暱稱", "Line名字", "LINE名字", "車款",
    *PHONE_LABELS, *NOTE_LABELS
)


@lru_cache(maxsize=256)
def normalize_text(text):
    """統一解析標點，並拆開常見的黏欄位。"""
    t = (
        text.replace("\u3000", " ")
            .replace("：", ":")
            .replace("；", ":")
            .replace("／", "/")
    )

    # 下車地址:潮汽車旅館。人數:1
    t = re.sub(
        r"[。．]\s*(?=(?:叫車日期|日期|時間|人數|乘坐人數|乘車人數|"
        r"手機|手機號碼|電話|TEL|連絡電話|聯絡電話|"
        r"行李數量|行李數|行李箱|備註|備注|其他備註|其他備注|"
        r"車款|Line名字|LINE名字)\s*:)",
        "\n", t, flags=re.I
    )

    # 地址後直接黏「目的地/目地」
    t = re.sub(
        r"(?<=[號巷弄路街區市廈口）)])\s*(?=(?:目的地|目地)\s*:)",
        "\n", t
    )
    return t

def is_noise_line(line):
    s = line.strip()
    if not s:
        return False
    return any(re.search(p, s, re.I) for p in NOISE_PATTERNS)


def is_booking_text(text):
    keywords = [
        "上車", "下車", "上車地", "下車地", "上車地點", "下車地點",
        "⬆️", "⬆", "🔽", "🔺", "🔻", "出發", "出發地", "起點", "到達", "終點",
        "目的", "目地", "日期", "叫車日期", "時間", "預約", "代駕",
        "人數", "乘坐人數", "乘車人數",
        "機場", "桃機", "航廈", "接機", "送機", "航班",
        "行李", "💰", "$", "＄", "固定"
    ]
    if any(k in text for k in keywords):
        return True

    t = normalize_text(text)

    if re.search(r"(?m)^\s*\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}", t):
        return True

    if re.search(r"(?m)^\s*\d{1,2}:\d{2}\s*$", t):
        return True

    return False


def strip_label(line, labels):
    s = line.strip()

    for label in sorted(labels, key=len, reverse=True):
        if not s.startswith(label):
            continue

        rest = s[len(label):]

        # 單字標籤特別處理：
        # 允許「上信義區松仁路88號」這種直接接地址的格式，
        # 但不能把「下午5:20」誤認成「下 + 地址」。
        if label in {"上", "下", "起"} and rest:
            if re.match(r"^[\s:：；●]", rest):
                pass
            else:
                if label == "下" and rest.startswith("午"):
                    continue

                if not looks_like_address(rest):
                    continue

        rest = re.sub(r"^\s*[:：；●]?\s*", "", rest)
        return True, rest.strip()

    return False, s

def looks_like_address(value):
    s = value.strip()
    if not s or is_noise_line(s):
        return False

    # 排除明顯非地址欄位/數值
    if re.match(r"^(?:\d+\s*人|\d+\s*(?:個|件|箱)?\s*行李|💰?\s*\d+\s*元?)$", s):
        return False
    if re.match(r"^\d{1,2}:\d{2}$", normalize_text(s)):
        return False

    if re.search(r"(路|街|巷|弄|號|區|鄉|鎮|市|村|里|機場|航廈|桃機|車站|飯店|酒店|旅館|汽車旅館|大樓|巷口|門口)", s):
        return True

    if re.search(r"(拉麵|餐廳|KTV|百貨|醫院|學校|夜市|捷運|高鐵|錢櫃)", s, re.I):
        return True

    # 常用裸地名
    return s in {
        "士林", "信義", "板橋", "新莊", "三重", "中和", "永和",
        "土城", "樹林", "汐止", "新店", "淡水", "內湖", "南港",
        "北投", "萬華", "桃園", "中壢"
    }


def looks_like_address_fragment(value):
    """已在地址區塊裡時，允許比較短的續行片段。"""
    s = value.strip()
    if not s or is_noise_line(s):
        return False
    if s.startswith(("(", "（")) and s.endswith((")", "）")):
        return True
    if re.match(r"^-?\d[\d\-]*$", s):
        return False
    if re.match(r"^\d+\s*(?:人|行李|元)$", s):
        return False
    if re.match(r"^-\d+", s):  # 斷行電話，例如 -959
        return False
    return bool(re.search(r"(路|街|巷|弄|號|區|鄉|鎮|市|里|村|口|門口|航廈|機場)", s))



def reorder_reversed_address(addr):
    """
    A) 民德路清穗里中和區新北市235 -> 新北市中和區清穗里民德路235
    B) 民德路234號清穗里中和區新北市235 -> 新北市中和區清穗里民德路234號
    """
    s = addr.strip()

    # B：前半已有明確門牌，尾端三碼視為郵遞區號
    m = re.fullmatch(
        r"(?P<road>.+?\d+(?:-\d+)?號)"
        r"(?P<village>[^號\d]{1,8}里)"
        r"(?P<district>[^里\d]{1,4}區)"
        r"(?P<city>台北市|臺北市|新北市|桃園市)"
        r"(?P<postal>\d{3})",
        s
    )
    if m:
        return (
            f"{m.group('city')}{m.group('district')}"
            f"{m.group('village')}{m.group('road')}"
        )

    # A：原本沒有「號」，最後數字視為地址號碼
    m = re.fullmatch(
        r"(?P<road>.+?(?:路|街|大道)(?:[一二三四五六七八九十0-9]+段)?)"
        r"(?P<village>[^號\d]{1,8}里)"
        r"(?P<district>[^里\d]{1,4}區)"
        r"(?P<city>台北市|臺北市|新北市|桃園市)"
        r"(?P<number>\d+(?:-\d+)?)",
        s
    )
    if m:
        return (
            f"{m.group('city')}{m.group('district')}"
            f"{m.group('village')}{m.group('road')}{m.group('number')}"
        )

    return s

def clean_address(addr):
    s = reorder_reversed_address(addr.strip())
    s = re.sub(r"^[：:；●\s]+", "", s)

    # 多點編號
    s = re.sub(
        r"^(?:\(加?\d+\)|（加?\d+）|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、]|"
        r"[1-9](?=[\u4e00-\u9fff]))\s*",
        "",
        s
    )

    # 若前方有明顯雜訊，但後面出現正式縣市/國名，從正式位置開始
    m = re.search(r"(台灣|臺灣|台北市|臺北市|新北市|桃園市)", s)
    if m and m.start() > 0:
        prefix_noise = s[:m.start()]
        # 正常郵遞區號或短雜訊都可丟棄；避免切掉真正路名
        if re.fullmatch(r"[\dA-Za-z骯髒亂碼\s]{1,8}", prefix_noise) or re.fullmatch(r"\d{3,6}", prefix_noise):
            s = s[m.start():]

    # 郵遞區號 3~6 碼
    s = re.sub(r"^\d{3,6}(?=[\u4e00-\u9fff])", "", s)

    # 國名/縣市
    s = re.sub(r"^(?:台灣|臺灣)", "", s)
    s = re.sub(r"^(?:台北市|臺北市|新北市|桃園市|北市)", "", s)
    s = re.sub(r"^(?:台北|臺北|新北)(?=[\u4e00-\u9fff]{1,4}區)", "", s)

    known_districts = (
        "中山|松山|大同|萬華|信義|內湖|南港|士林|北投|文山|中正|大安|"
        "板橋|新莊|三重|中和|永和|土城|樹林|汐止|蘆洲|泰山|林口|淡水|"
        "新店|五股|深坑|三峽|鶯歌|瑞芳|金山|萬里|中壢|平鎮|八德|龜山|"
        "蘆竹|大溪|楊梅|龍潭|大園|觀音|新屋"
    )
    s = re.sub(rf"^市(?=(?:{known_districts})區)", "", s)

    # 行政區後面的里名
    s = re.sub(r"(?<=[區鄉鎮市])[\u4e00-\u9fff]{1,8}里", "", s)

    # 航廈
    s = re.sub(r"(第一|第二)航(?!廈)", r"\1航廈", s)
    if re.fullmatch(r"第一航廈", s):
        s = "桃園第一航廈"
    elif re.fullmatch(r"第二航廈", s):
        s = "桃園第二航廈"
    elif re.fullmatch(r"(?i:T1)", s):
        s = "桃園第一航廈"
    elif re.fullmatch(r"(?i:T2)", s):
        s = "桃園第二航廈"

    # 常見行政區省略「區」：只在後面明顯接道路時補，避免「中正路」誤變中正區路
    districts = [
        "中山", "松山", "大同", "萬華", "信義", "內湖", "南港", "士林",
        "北投", "文山", "中正", "大安", "板橋", "新莊", "三重", "中和",
        "永和", "土城", "樹林", "汐止", "蘆洲", "泰山", "林口", "淡水",
        "新店", "五股", "深坑", "三峽", "鶯歌", "瑞芳", "金山", "萬里",
        "中壢", "平鎮", "八德", "龜山", "蘆竹", "大溪", "楊梅", "龍潭",
        "大園", "觀音", "新屋"
    ]
    for d in sorted(districts, key=len, reverse=True):
        if s.startswith(d) and not s.startswith(d + "區"):
            tail = s[len(d):]
            # 裸地名與地標不補；「中正路」這類路名也不補
            if (
                tail
                and not re.match(r"^(?:路|街|巷|弄)", tail)
                and re.search(r"(路|街|巷|弄|號)", tail)
                and not re.search(r"(拉麵|餐廳|KTV|百貨|醫院|學校|夜市|捷運)", s)
            ):
                s = d + "區" + tail
            break

    if re.search(r"(路|街|巷|弄|號|航廈|機場|旅館|飯店|社區)", s):
        s = re.sub(r"(?:上車|下車|地址|地點)$", "", s)

    s = re.sub(r"\s+", "", s)
    return s.strip()


def parse_date(text):
    t = normalize_text(text)
    now = datetime.now(ZoneInfo("Asia/Taipei"))

    date_label = r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    if re.search(
        rf"{date_label}\s*:\s*(?:當日免填|今日免填|今天|今日|現在|立即|馬上|立刻)",
        t
    ):
        return ""

    m = re.search(rf"{date_label}\s*:\s*(\d{{4}})[/-](\d{{1,2}})[/-](\d{{1,2}})", t)
    if m:
        month, day = int(m.group(2)), int(m.group(3))
        if (month, day) == (now.month, now.day):
            return ""
        return f"{month}/{day}"

    m = re.search(rf"{date_label}\s*:\s*(\d{{1,2}})[/-](\d{{1,2}})", t)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if (month, day) == (now.month, now.day):
            return ""
        return f"{month}/{day}"

    # 極簡：8/30 TG634
    m = re.search(
        r"(?m)^\s*(\d{1,2})[/-](\d{1,2})"
        r"(?=\s+(?:[A-Za-z]{1,3}\d{2,4}|\d[A-Za-z]\d{2,4})\b)",
        t, re.I
    )
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if (month, day) == (now.month, now.day):
            return ""
        return f"{month}/{day}"

    # 極簡：8/26 03:30 ...
    m = re.search(r"(?m)^\s*(\d{1,2})[/-](\d{1,2})(?=\s+(?:\d{1,2}:\d{2}|\d{4})\b)", t)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if (month, day) == (now.month, now.day):
            return ""
        return f"{month}/{day}"

    return ""


def convert_time(period, hour, minute):
    if period in ("下午", "晚上") and hour < 12:
        hour += 12
    elif period == "中午" and hour < 12:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0
    return hour, minute


def nearest_ambiguous_hour(hour):
    from datetime import timedelta
    now = datetime.now(ZoneInfo("Asia/Taipei"))

    if hour == 12:
        choices = [0, 12]
    elif 1 <= hour <= 11:
        choices = [hour, hour + 12]
    else:
        return hour

    candidates = []
    for h in choices:
        dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        candidates.append(dt)

    return min(candidates).hour


def _booking_target_datetime(text, hour, minute):
    """建立預約時間；明確日期優先，否則以今天/最近時刻判斷。"""
    from datetime import timedelta

    t = normalize_text(text)
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    target_date = now.date()
    explicit_date = False

    m = re.search(
        r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?\s*:\s*"
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
        t
    )
    if m:
        try:
            target_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            explicit_date = True
        except ValueError:
            pass
    else:
        m = re.search(
            r"(?:叫車日期|日期)(?:\s*\([^)]*\)|\s*（[^）]*）)?\s*:\s*"
            r"(\d{1,2})[/-](\d{1,2})",
            t
        )
        if not m:
            m = re.search(r"(?m)^\s*(\d{1,2})[/-](\d{1,2})(?=\s+\d{1,2}:\d{2})", t)

        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = now.year
            if now.month == 12 and month == 1:
                year += 1
            elif now.month == 1 and month == 12:
                year -= 1
            try:
                target_date = datetime(year, month, day).date()
                explicit_date = True
            except ValueError:
                pass

    target = datetime(
        target_date.year, target_date.month, target_date.day,
        hour, minute, tzinfo=ZoneInfo("Asia/Taipei")
    )

    # 無明確日期：若是「今日」則不跨日；一般時刻允許午夜跨日
    has_today_word = bool(re.search(r"(?:時間\s*:?\s*)?今日", t))
    if not explicit_date and not has_today_word:
        # 只在「明顯是下一個午夜時刻」時跨日。
        # 過去 10 分鐘內的時間保留今天，讓 ±10 分鐘規則能正常工作。
        if target < now and (now - target).total_seconds() > 10 * 60:
            if now.hour >= 18 and hour <= 6:
                target += timedelta(days=1)

    return target


def format_time_with_10min_rule(text, hour, minute):
    """
    與現在時間前後 10 分鐘內（含）不顯示。
    例如現在 01:15：01:10、01:20 都隱藏。
    """
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    target = _booking_target_datetime(text, hour, minute)
    diff = abs((target - now).total_seconds()) / 60

    if diff <= 10:
        return ""
    return f"{hour:02d}:{minute:02d}"


def parse_time(text):
    t = normalize_text(text)
    label = r"(?:時間|上車時間)(?:\s*\([^)]*\)|\s*（[^）]*）)?"

    # 空白 / 即時
    if re.search(
        rf"(?m)^{label}\s*:\s*(?:現在|即時免填|現在免填|立即|馬上|立刻|24H|24h|全天|全天候)?\s*$",
        t
    ):
        return ""

    # 上車時間若其實填地址，不當成時間
    m = re.search(r"(?m)^上車時間\s*:\s*(.+)$", t)
    if m and looks_like_address(m.group(1)):
        pass

    # 今日凌晨02:00 / 今日下午3:20
    m = re.search(
        rf"{label}\s*:\s*今日\s*(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{{1,2}})[:.](\d{{2}})",
        t
    )
    if m:
        hour, minute = convert_time(m.group(1) or "", int(m.group(2)), int(m.group(3)))
        return format_time_with_10min_rule(t, hour, minute)

    # 預約1:05
    m = re.search(r"預約\s*:?\s*(\d{1,2})[:.](\d{2})", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    # 等等2. / 等等2點 / 等2點
    m = re.search(
        rf"(?m)^{label}\s*:\s*(?:等等?|待會(?:兒)?)\s*(\d{{1,2}})\s*(?:點|[.。])?\s*$",
        t
    )
    if m:
        raw = int(m.group(1))
        hour = nearest_ambiguous_hour(raw) if 1 <= raw <= 12 else raw
        if 0 <= hour <= 23:
            return format_time_with_10min_rule(t, hour, 0)

    # 飛機抵達上午01:30 / 航班抵達凌晨02:20 / 抵達晚上9:40
    m = re.search(
        rf"{label}\s*:\s*(?:飛機抵達|航班抵達|抵達)?\s*"
        rf"(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{{1,2}})[:.](\d{{2}})",
        t
    )
    if m:
        hour, minute = convert_time(m.group(1) or "", int(m.group(2)), int(m.group(3)))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    # 無欄位標籤：下午5:20
    m = re.search(
        r"(?m)^\s*(凌晨|早上|上午|中午|下午|晚上)\s*(\d{1,2})[:.](\d{2})\s*$",
        t
    )
    if m:
        hour, minute = convert_time(m.group(1), int(m.group(2)), int(m.group(3)))
        return format_time_with_10min_rule(t, hour, minute)

    # 上午/下午/凌晨 + HH:MM
    m = re.search(
        rf"{label}\s*:\s*(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{{1,2}})[:.](\d{{2}})",
        t
    )
    if m:
        hour, minute = convert_time(m.group(1) or "", int(m.group(2)), int(m.group(3)))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    # 上午/下午 + 幾點
    m = re.search(
        rf"{label}\s*:\s*(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{{1,2}})\s*點",
        t
    )
    if m:
        period = m.group(1) or ""
        raw = int(m.group(2))
        if period:
            hour, minute = convert_time(period, raw, 0)
        else:
            hour, minute = nearest_ambiguous_hour(raw), 0
        return format_time_with_10min_rule(t, hour, minute)

    # 08:35pm
    m = re.search(rf"{label}\s*:\s*(\d{{1,2}})[:.](\d{{2}})\s*(am|pm)", t, re.I)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ap = m.group(3).lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
        return format_time_with_10min_rule(t, hour, minute)

    # 0500 / 1830
    m = re.search(rf"{label}\s*:\s*(\d{{2}})(\d{{2}})\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    # 極簡：8/26 03:30 ...
    m = re.search(r"(?m)^\s*\d{1,2}[/-]\d{1,2}\s+(\d{1,2})[:.](\d{2})\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        return format_time_with_10min_rule(t, hour, minute)

    # 極簡：8/9 2200
    m = re.search(r"(?m)^\s*\d{1,2}[/-]\d{1,2}\s+(\d{2})(\d{2})\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        return format_time_with_10min_rule(t, hour, minute)

    # 單獨一行 0500 / 1830 / 2300
    m = re.search(r"(?m)^\s*(\d{2})(\d{2})\s*$", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    # 單獨一行 04:30
    m = re.search(r"(?m)^\s*(\d{1,2})[:.](\d{2})\s*$", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return format_time_with_10min_rule(t, hour, minute)

    return ""


def parse_price(text):
    """
    金額必須有明確金額提示。
    純四碼（如 2300）優先視為時間，不當金額。
    """
    t = normalize_text(text)
    patterns = [
        r"固定\s*💰?\s*(\d+)",
        r"💰\s*(\d+)",
        r"[$＄]\s*(\d+)",
        r"(?m)^\s*錢\s*:?\s*(\d+)\s*$",
        r"(?m)^\s*收\s*:?\s*(\d+)\s*$",
        r"(?m)^\s*(\d{3,5})\s*元\s*$",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return f"💰{m.group(1)}"
    return ""

def chinese_num_to_int(s):
    mapping = {
        "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10
    }
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        a, b = s.split("十", 1)
        return mapping.get(a, 1) * 10 + mapping.get(b, 0)
    return mapping.get(s, 0)


def parse_people_count(text):
    t = normalize_text(text)

    m = re.search(
        r"(?m)^(?:人數|乘坐人數|乘車人數)\s*:\s*"
        r"([0-9一二兩三四五六七八九十]+)\s*(?:人)?",
        t
    )
    if m:
        n = chinese_num_to_int(m.group(1))
        return n if 0 < n <= 20 else 0

    m = re.search(r"([0-9一二兩三四五六七八九十]+)\s*人", t)
    if m:
        n = chinese_num_to_int(m.group(1))
        return n if 0 < n <= 20 else 0

    return 0


def parse_luggage(text):
    t = normalize_text(text)

    if re.search(r"(?m)^(?:行李數量|行李數|行李箱)\s*:\s*[XxＸｘ]\s*$", t):
        return ""

    m = re.search(
        r"(?m)^(?:行李數量|行李數|行李箱)\s*:\s*"
        r"(\d+)\s*(?:-|~|～|至)\s*(\d+)\s*(?:個|件|箱)?\s*$",
        t
    )
    if m:
        return f"🧳{m.group(1)}-{m.group(2)}件"

    m = re.search(r"(?m)^(?:行李數量|行李數|行李箱)\s*:\s*(\d+)\s*(?:個|件|箱)?\s*$", t)
    if m:
        n = int(m.group(1))
        return f"🧳{n}件" if n > 0 else ""

    m = re.search(r"\d+\s*人\s*(\d+)\s*(?:個|件|箱)?\s*行李", t)
    if m:
        n = int(m.group(1))
        return f"🧳{n}件" if n > 0 else ""

    m = re.search(r"(?<!\d)(\d+)\s*(?:-|~|～|至)\s*(\d+)\s*(?:個|件|箱)", t)
    if m:
        return f"🧳{m.group(1)}-{m.group(2)}件"

    m = re.search(r"(\d+)\s*(?:個|件|箱)\s*(?:\d{2}\s*吋)?\s*行李", t)
    if m:
        return f"🧳{int(m.group(1))}件"

    size_items = re.findall(r"\d{2}\s*吋\s*(\d+)\s*(?:個|件|箱)?", t)
    if size_items:
        return f"🧳{sum(int(x) for x in size_items)}件"

    return ""


def parse_booking_type(text):
    """目前需保留顯示的服務類型。"""
    t = normalize_text(text)
    if "代駕預約" in t or re.search(r"(?m)^\s*代駕\s*$", t):
        return "代駕"
    return ""


def parse_vehicle_info(text):
    """七座車型，不與乘客人數混用。"""
    t = normalize_text(text)
    m = re.search(
        r"(?:七人座|七座|7人座|7座)\s*(?:➕|\+|加)?\s*(\d{2,5})?",
        t
    )
    if not m:
        return ""
    extra = m.group(1)
    return f"七座+{extra}" if extra else "七座"


def is_phone_only(value):
    compact = re.sub(r"[\s\-()（）]", "", value or "")
    return bool(re.fullmatch(r"(?:\+?886)?0?\d{8,10}", compact))


def parse_airport_info(text):
    t = normalize_text(text)

    service = ""
    m = re.search(r"(?:接機\s*/\s*送機|接機送機)\s*:\s*(接機|送機)", t)
    if m:
        service = m.group(1)
    else:
        m = re.search(r"(?<![/])(接機|送機)", t)
        if m:
            service = m.group(1)

    flight = ""
    m = re.search(
        r"(?:航班|航班編號|航班號碼)\s*:\s*[^\n]*?"
        r"(?<![A-Za-z0-9])((?:[A-Za-z]{1,3}\d{2,4}|\d[A-Za-z]\d{2,4}))(?![A-Za-z0-9])",
        t, re.I
    )
    if m:
        flight = m.group(1).upper()
    elif re.search(r"(接機|送機|機場|航廈|桃機)", t):
        m = re.search(
            r"(?<![A-Za-z0-9])((?:[A-Za-z]{1,3}\d{2,4}|\d[A-Za-z]\d{2,4}))(?![A-Za-z0-9])",
            t, re.I
        )
        if m:
            flight = m.group(1).upper()

    return service, flight


def parse_notes(text):
    """解析備註；純電話號碼視為聯絡資訊，不顯示。"""
    lines = [x.strip() for x in normalize_text(text).splitlines()]
    ignore = {
        "0", "無", "沒有", "無備註", "無備注", "無行李", "沒行李",
        "免備註", "免備注", "不用", "正常", "一般", "皆可",
        "N", "n", "NO", "No", "no", "-", "--", "免",
        "X", "x", "Ｘ", "ｘ"
    }

    collected = []
    collecting = False

    for line in lines:
        hit, rest = strip_label(line, NOTE_LABELS)
        if hit:
            collecting = True
            if rest:
                collected.append(rest)
            continue

        if collecting:
            if not line:
                continue
            if is_noise_line(line):
                continue

            if any(line.startswith(p) for p in FIELD_PREFIXES if p not in NOTE_LABELS):
                break
            if any(line.startswith(p) for p in PICKUP_LABELS + DROPOFF_LABELS):
                break
            collected.append(line)

    if not collected:
        for line in lines:
            if line.startswith("✅") and len(line) > 1:
                collected.append(line)

    parts = []
    for raw in collected:
        s = raw.strip()
        if not s or s in ignore or is_noise_line(s) or is_phone_only(s):
            continue

        s = re.sub(r"(^|[\s，,、/]+)(接機|送機)(?=$|[\s，,、/]+)", " ", s)
        s = re.sub(r"([0-9一二兩三四五六七八九十]+)\s*(?:個)?人", " ", s)
        s = re.sub(r"\d+\s*(?:個|件|箱)\s*(?:\d{2}\s*吋)?\s*行李", " ", s)

        if re.match(r"^(?:💰|[$＄]|固定|錢|收)\s*:?\s*\d+", s):
            continue

        if s.startswith("✅"):
            payload = s.lstrip("✅").strip()
            if payload and payload not in ignore and not is_phone_only(payload):
                parts.append(f"✅{payload}")
            continue

        chunks = [c.strip() for c in re.split(r"[，,、/]+", s) if c.strip()]
        for c in chunks:
            if not c or c in ignore or is_phone_only(c):
                continue
            if " " in c:
                for token in [x for x in c.split() if x]:
                    if token not in ignore and not is_phone_only(token):
                        parts.append(f"✅{token}")
            else:
                parts.append(f"✅{c}")

    # 金額後黏備註
    m = re.search(r"(?:💰|[$＄])\s*\d+\s*([^\n\d].*)$", normalize_text(text), re.MULTILINE)
    if m:
        suffix = m.group(1).strip()
        if suffix and suffix not in ignore and not is_noise_line(suffix) and not is_phone_only(suffix):
            tag = f"✅{suffix}"
            if tag not in parts:
                parts.append(tag)

    # 去重
    seen, unique = set(), []
    for item in parts:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return "".join(unique)

def parse_addresses(text):
    """
    地址流程：
    1) 先正規化/拆黏欄位
    2) 再辨識上/下車標籤
    3) 最後才做地址清理
    """
    source = normalize_text(text)
    lines = [x.strip() for x in source.splitlines() if x.strip()]
    pickups, dropoffs = [], []

    current_mode = None
    current_parts = []
    skip_phone_continuation = False

    def append_clean(mode, value):
        cleaned = clean_address(value)
        if not cleaned:
            return
        (pickups if mode == "pickup" else dropoffs).append(cleaned)

    def split_drop_sequence(value):
        s = value.strip()
        s = re.sub(r"^先到", "", s)
        parts = [x.strip() for x in re.split(r"再到", s) if x.strip()]
        return parts if parts else []

    def flush():
        nonlocal current_parts
        if not current_parts or current_mode not in ("pickup", "dropoff"):
            current_parts = []
            return

        merged = re.sub(r"\s+", "", "".join(current_parts))

        if current_mode == "dropoff" and ("先到" in merged or "再到" in merged):
            for point in split_drop_sequence(merged):
                append_clean("dropoff", point)
        else:
            append_clean(current_mode, merged)
        current_parts = []

    for raw in lines:
        line = raw.strip()

        # 人數相關文字不能被當成地址或額外下車點
        if re.fullmatch(
            r"(?:人|人數|乘坐人數|乘車人數|乘客人數|"
            r"\d+\s*人(?:\s*[+➕＋]\s*\d+)?|"
            r"[一二兩三四五六七八九十]+\s*人)",
            line
        ):
            flush()
            current_mode = None
            continue

        if is_noise_line(line):
            continue

        # 額外資訊欄，不讓它被地址解析吃掉
        if re.match(r"^(?:Line名字|LINE名字|Line匿稱|Line暱稱|車款)\s*:", line, re.I):
            flush()
            current_mode = None
            continue

        # 電話欄及斷行 continuation
        if any(line.startswith(p) for p in PHONE_LABELS):
            flush()
            current_mode = None
            skip_phone_continuation = True
            continue

        if skip_phone_continuation:
            if re.match(r"^-?[\d\- ]+$", line):
                continue
            skip_phone_continuation = False

        # 上車時間誤填地址
        if line.startswith("上車時間"):
            hit, value = strip_label(line, ("上車時間",))
            if value and looks_like_address(value):
                flush()
                current_mode = "pickup"
                current_parts = [value]
                continue
            flush()
            current_mode = None
            continue

        hit, value = strip_label(line, PICKUP_LABELS)
        if hit:
            flush()
            current_mode = "pickup"
            current_parts = [value] if value else []
            continue

        hit, value = strip_label(line, DROPOFF_LABELS)
        if hit:
            flush()
            if value and (value.startswith("先到") or "再到" in value):
                for point in split_drop_sequence(value):
                    append_clean("dropoff", point)
                current_mode = None
                current_parts = []
            else:
                current_mode = "dropoff"
                current_parts = [value] if value else []
            continue

        if any(line.startswith(p) for p in FIELD_PREFIXES):
            flush()
            current_mode = None
            continue

        if current_mode in ("pickup", "dropoff") and re.match(
            r"^(?:\(加?\d+\)|（加?\d+）|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、]|[1-9](?=[\u4e00-\u9fff]))",
            line
        ):
            flush()
            current_parts = [line]
            continue

        if current_mode in ("pickup", "dropoff"):
            if line.startswith(("(", "（")) or looks_like_address_fragment(line) or looks_like_address(line):
                current_parts.append(line)
                continue
            flush()
            current_mode = None

    flush()

    # 無標籤格式：第一個地址上車，其餘下車
    if not pickups and not dropoffs:
        candidates = []
        for line in lines:
            t = normalize_text(line)

            if is_noise_line(line):
                continue
            if re.match(r"^\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}", t):
                continue
            if re.match(r"^\d{1,2}:\d{2}$", t):
                continue
            if re.fullmatch(r"\d{4}", t):
                hh, mm = int(t[:2]), int(t[2:])
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    continue
            if re.fullmatch(
                r"(?:人|人數|乘坐人數|乘車人數|乘客人數|"
                r"\d+\s*人(?:\s*[+➕＋]\s*\d+)?|"
                r"[一二兩三四五六七八九十]+\s*人)",
                t
            ):
                continue
            if re.match(r"^(?:💰?\s*)?\d+\s*元?$", t):
                continue
            if re.fullmatch(r"\d{8,12}", re.sub(r"[-\s]", "", t)):
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]{1,4}(?:先生|小姐|女士)", t):
                continue
            if "行李" in line and re.search(r"\d", line):
                continue
            if re.match(r"^(?:Line名字|LINE名字|Line匿稱|Line暱稱|車款)\s*:", line, re.I):
                continue

            if looks_like_address(line):
                candidates.append(clean_address(line))

        if candidates:
            pickups.append(candidates[0])
            dropoffs.extend(candidates[1:])

    return pickups, dropoffs

def is_airport_booking(text, service, pickups, dropoffs):
    if service in ("接機", "送機"):
        return True
    combined = "\n".join(pickups + dropoffs) + "\n" + text
    return bool(re.search(r"(桃園(?:國際)?機場|桃機|第一航廈|第二航廈|\bT1\b|\bT2\b|機場)", combined, re.I))



def parse_people_extra(text):
    """
    不自動計算人數加價。
    只有原文明確出現「5人 +100 / 5人➕100 / 5人 加100」才保留。
    七座/七人座車型加價不屬於這裡。
    """
    t = normalize_text(text)

    m = re.search(
        r"([0-9一二兩三四五六七八九十]+)\s*人\s*"
        r"(?:\+|➕|＋|加)\s*(\d{2,5})",
        t
    )
    if m:
        return f"+{m.group(2)}"

    return ""


def parse_booking_data(text):
    """
    單一解析入口。
    同一張 LINE 訂單只建立一次結構化資料，完整訊息與額外訊息共用。
    """
    source = normalize_text(text)

    # 先解析相互依賴的欄位
    service, flight = parse_airport_info(source)
    pickups, dropoffs = parse_addresses(source)

    data = {
        "source": source,
        "date": parse_date(source),
        "time": parse_time(source),
        "price": parse_price(source),
        "note": parse_notes(source),
        "booking_type": parse_booking_type(source),
        "vehicle": parse_vehicle_info(source),
        "people_extra": parse_people_extra(source),
        "service": service,
        "flight": flight,
        "pickups": pickups,
        "dropoffs": dropoffs,
        "people": parse_people_count(source),
        "luggage": parse_luggage(source),
    }

    data["airport"] = is_airport_booking(
        source,
        data["service"],
        data["pickups"],
        data["dropoffs"]
    )

    return data


def format_booking_data(data):
    """只負責格式化，不重新解析原文。"""
    output = []

    first = [
        x for x in (
            data["date"],
            data["time"],
            data["booking_type"],
            data["service"],
            data["flight"],
        )
        if x
    ]
    if first:
        output.append(" ".join(first))

    for pickup in data["pickups"]:
        output.append(f"⬆️{pickup}")

    if data["dropoffs"]:
        output.append(f"下車地點：{data['dropoffs'][0]}")
        for dropoff in data["dropoffs"][1:]:
            output.append(f"🔽{dropoff}")

    if data["vehicle"]:
        output.append(data["vehicle"])

    info = []

    if data["airport"]:
        if data["people"] > 0:
            info.append(f"{data['people']}人")
        if data["luggage"]:
            info.append(data["luggage"])
    else:
        if data["people"] > 4:
            people_text = f"{data['people']}人"
            if data["people_extra"]:
                people_text += f" {data['people_extra']}"
            info.append(people_text)

    if data["note"]:
        info.append(data["note"])

    if info:
        output.append("｜".join(info))

    if data["price"]:
        output.append(data["price"])

    return "\n".join(output).strip()


def format_booking(text):
    """
    保留舊函式介面，方便既有測試/其他程式呼叫。
    實際解析統一走 parse_booking_data()。
    """
    return format_booking_data(parse_booking_data(text))


def build_reply_texts(text):
    """
    同一張單只 parse_booking_data() 一次。

    1 完整簡化
    2 上車地；代駕/備註也顯示
    3 取消 上車地
    4 有有效預約時間：*時間；代駕/備註也顯示
    """
    data = parse_booking_data(text)
    result = format_booking_data(data)

    if not result:
        return []

    replies = [result]

    if not data["pickups"]:
        return replies

    pickup = data["pickups"][0]

    # 第二則：帶代駕、上車地、附加資訊與備註
    second = []
    if data["booking_type"]:
        second.append(data["booking_type"])
    second.append(f"⬆️{pickup}")
    if data["vehicle"]:
        second.append(data["vehicle"])
    if data["note"]:
        second.append(data["note"])
    replies.append("\n".join(second))

    # 第三則
    replies.append(f"取消 {pickup}")

    # 第四則
    if data["time"]:
        first_line = f"*{data['time']}"
        if data["booking_type"]:
            first_line += f" {data['booking_type']}"

        fourth = [first_line, f"⬆️{pickup}"]
        if data["vehicle"]:
            fourth.append(data["vehicle"])
        if data["note"]:
            fourth.append(data["note"])
        replies.append("\n".join(fourth))

    return replies[:4]


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

    replies = build_reply_texts(text)

    if not replies:
        return

    line_bot_api.reply_message(
        event.reply_token,
        [TextSendMessage(text=item) for item in replies]
    )


notify_startup()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))