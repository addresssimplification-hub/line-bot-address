from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

APP_FILE = Path(__file__).with_name("app_v3.6.0.py")
text = APP_FILE.read_text(encoding="utf-8")
compile(text, str(APP_FILE), "exec")

# 只載入純 Parser / formatter 區塊，不觸發 LINE startup push。
logic_start = text.index("NOISE_PATTERNS =")
logic_end = text.index('@app.route("/", methods=["GET"])', logic_start)

ns = {}
exec(
    "import re\n"
    "from functools import lru_cache\n"
    "from datetime import datetime, timedelta\n"
    "from zoneinfo import ZoneInfo\n"
    + text[logic_start:logic_end],
    ns
)

failed = []

def exact(name, raw, expected):
    actual = ns["format_booking"](raw)
    ok = actual == expected
    print(f"[{name}] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("ACTUAL:")
        print(actual)
        print("EXPECTED:")
        print(expected)
        failed.append(name)

def contains(name, raw, must=(), must_not=()):
    actual = ns["format_booking"](raw)
    ok = all(x in actual for x in must) and all(x not in actual for x in must_not)
    print(f"[{name}] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(actual)
        failed.append(name)

# 1. 雙行政區 + 里鄰 + 固定提醒
exact(
    "雙行政區_里鄰_固定提醒",
    """日期：當日免填
時間：現在免填（24小時制）
上車地址：桃園區龍潭區中正里15鄰中正路472號
下車地址：新北市三重區正義南路67號
手機號碼：0958176037
行李數量：2
其他備註：
‼️麻煩完整地址電話提供‼️
‼️電話未提供不派車‼️""",
    """⬆️龍潭區中正路472號
下車地點：三重區正義南路67號"""
)

# 2. 獨立 上 / 下
exact(
    "獨立上下標籤",
    """上
板橋中山路二段443號
下
新北市新莊區豐年里豐年街118之1號""",
    """⬆️板橋區中山路二段443號
下車地點：新莊區豐年街118之1號"""
)

# 3. 北市 / 跨行 / 斷電話 / 括號地標
exact(
    "北市跨行地址",
    """日期：當日免填
時間：01：55

上車地址：北市民生西路
305號
（中華電信門口）

下車地址：
新北市新莊區
福美街62巷
2號

乘坐人數：1
手機號碼：0955-555
-959

其他備註：
無煙車""",
    """01:55
⬆️民生西路305號（中華電信門口）
下車地點：新莊區福美街62巷2號
✅無煙車"""
)

# 4. 機場雙上車 + 行李簡寫
exact(
    "機場雙上車",
    """10/22 06:50 送機 9C8952
⬆️吳興街269巷1弄22號
⬆️萬芳醫院對面
下車地點：桃園機場第一航廈
人數：4
行李：3""",
    """10/22 06:50 送機 9C8952
⬆️吳興街269巷1弄22號
⬆️萬芳醫院對面
下車地點：桃園機場第一航廈
4人｜🧳3件"""
)

# 5. 第一 / 第二下車
exact(
    "第一第二下車",
    """日期：當日免填
時間：現在
上車地址：臺北市萬華區福星里西寧南路65號
第一下車地址：新北市新莊區五工三路78巷11號
第二下車地址：新北市土城區慶利街18號
乘坐人數：2
手機號碼：0925010298
行李數量：
其他備註：""",
    """⬆️萬華區西寧南路65號
下車地點：新莊區五工三路78巷11號
🔽土城區慶利街18號"""
)

# 6. 上： / 下：
exact(
    "單字冒號標籤",
    """上：105臺北市松山區敦化里市民大道四段103號
下：110臺北市信義區西村里松壽路18號B1""",
    """⬆️松山區市民大道四段103號
下車地點：信義區松壽路18號B1"""
)

# 7. 上🚘 / 下🚘
exact(
    "emoji上下標籤",
    """上🚘：台北市中山區中山北路二段112號
下🚘：新北蘆洲區中華街6巷52號
時間：現在
人數：1
備註：無
＝＝＝＝＝＝＝＝＝＝＝""",
    """⬆️中山區中山北路二段112號
下車地點：蘆洲區中華街6巷52號"""
)

# 8. 日期無冒號 + 上下車點
exact(
    "日期無冒號_箭頭",
    """日期9/13
時間：1:50
姓名：龔姵如
電話：0955312944
⬆️上車點：板橋南門街61號
⬇️下車點：樹林東陽街53號
人數：1
備註：""",
    """9/13 01:50
⬆️板橋區南門街61號
下車地點：樹林區東陽街53號"""
)

# 9. 日期時間混合 + 行李星號
exact(
    "日期時間_行李星號",
    """9/13早上 10:15分
桃園市桃園區大興西路二段176號
到
松山機場
7人 23寸行李箱*5 19寸*1
💰1300""",
    """9/13 10:15
⬆️桃園區大興西路二段176號
下車地點：松山機場
7人｜🧳6件
💰1300"""
)

# 10. 中山北路不可誤補區
exact(
    "中山北路保護",
    """上車地址：台北市中山北路一段105巷16之2號""",
    """⬆️中山北路一段105巷16之2號"""
)

# 11. 地標 + 完整地址跨行
exact(
    "地標跨行",
    """時間：1:30
上車地址：diablo bar
臺北市中山區正得里中山北路一段135巷21號
下車地址：輔大文藝門
其他備註：無""",
    """01:30
⬆️diablo bar 中山區中山北路一段135巷21號
下車地點：輔大文藝門"""
)

# 12. 舊版：單日日期
now = datetime.now(ZoneInfo("Asia/Taipei"))
test_day = 28 if now.day != 28 else 27
contains(
    "單日日期",
    f"""日期：{test_day}號
時間：18:30
上車：板橋區文化路一段1號
下車：新莊區中正路2號""",
    must=(f"{now.month}/{test_day} 18:30",)
)

# 13. 舊版：0600pm
contains(
    "compact_AMPM",
    """日期：12/25
時間：0600pm
上車：板橋區文化路一段1號
下車：新莊區中正路2號""",
    must=("12/25 18:00",)
)

# 14. 2大2小
contains(
    "2大2小",
    """接機
上車：桃園機場第一航廈
下車：信義區松仁路88號
乘坐人數：2大2小
行李數量：2""",
    must=("4人｜🧳2件",)
)

# 15. 人數規則
contains(
    "5人不自動加價",
    """上車：士林區福壽街12號
下車：中正區臨沂街34號
5人""",
    must=("5人",),
    must_not=("+100",)
)
contains(
    "5人明確加價",
    """上車：士林區福壽街12號
下車：中正區臨沂街34號
5人 +100""",
    must=("5人 +100",)
)

# 16. 七座
contains(
    "七座",
    """上車：士林區福壽街12號
下車：中正區臨沂街34號
七座+300""",
    must=("七座+300",),
    must_not=("7人",)
)

# 17. 2300 是時間
contains(
    "2300是時間",
    """2300
出發地：基隆市健民街32巷1弄口
目的地：桃園市觀音區草漯九如街135號""",
    must=("23:00", "⬆️基隆市健民街32巷1弄口", "下車地點：觀音區草漯九如街135號"),
    must_not=("💰2300",)
)

# 18. 金額後黏備註
contains(
    "金額後黏備註",
    """上車：板橋區文化路一段1號
下車：新莊區中正路2號
💰1300客下轉""",
    must=("💰1300", "✅客下轉")
)

# 19. 同行多下車
exact(
    "同行多下車",
    "⬆️永和區永和路一段100號目地:先到仁愛路38號再到台北市信義區忠孝東路五段295巷6弄30號",
    """⬆️永和區永和路一段100號
下車地點：仁愛路38號
🔽信義區忠孝東路五段295巷6弄30號"""
)

# 20. 反向地址
contains(
    "反向地址",
    """上車：民德路234號清穗里中和區新北市235
下車：板橋區文化路一段1號""",
    must=("⬆️中和區民德路234號",)
)

# 21. 代駕
contains(
    "代駕",
    """代駕預約
日期：現在免填
時間：現在免填（24H)
上車：思源路311號
下車：新莊區新樹路699巷""",
    must=("代駕", "⬆️思源路311號", "下車地點：新莊區新樹路699巷")
)

# 22. 四則回覆 + 附加資訊
raw = """日期：12/25
時間：18:30
上車：士林區福壽街12號
下車：中正區臨沂街34號
七座+300
備註：越快越好"""
replies = ns["build_reply_texts"](raw)
ok = (
    len(replies) == 4
    and replies[1] == "⬆️士林區福壽街12號\n七座+300\n✅越快越好"
    and replies[2] == "取消 士林區福壽街12號"
    and replies[3] == "*18:30\n⬆️士林區福壽街12號\n七座+300\n✅越快越好"
)
print("[四則回覆] " + ("PASS" if ok else "FAIL"))
if not ok:
    print(replies)
    failed.append("四則回覆")

# 23. 效能：build_reply_texts 只呼叫一次 parse_booking_data
original_parse = ns["parse_booking_data"]
counter = {"n": 0}

def counted_parse(source):
    counter["n"] += 1
    return original_parse(source)

ns["build_reply_texts"].__globals__["parse_booking_data"] = counted_parse
ns["build_reply_texts"](raw)
ns["build_reply_texts"].__globals__["parse_booking_data"] = original_parse

ok = counter["n"] == 1
print("[單次解析] " + ("PASS" if ok else "FAIL"))
if not ok:
    failed.append("單次解析")

# 24. normalize cache 存在
ns["normalize_text"].cache_clear()
ns["normalize_text"]("測試")
ns["normalize_text"]("測試")
cache_info = ns["normalize_text"].cache_info()
ok = cache_info.hits >= 1
print("[normalize cache] " + ("PASS" if ok else "FAIL"))
if not ok:
    failed.append("normalize cache")

if failed:
    raise SystemExit("FAIL: " + ", ".join(failed))

print("\n全部回歸測試 PASS")
