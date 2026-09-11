# -*- coding: utf-8 -*-
"""
AI 资讯自动推送到手机
======================

数据来源：
    https://aihot.virxact.com

功能：
    1. 获取 AI HOT 日报
    2. 自动统计各分类新闻数量
    3. 使用字符图形生成简单的数据可视化
    4. 自动整理 TOP STORY
    5. 自动限制新闻数量，避免 Bark 通知过长
    6. Bark 推送到 iPhone
    7. 支持 Server 酱
    8. 支持 Email
    9. 支持 .env
    10. 支持 GitHub Actions

推荐：
    GitHub Actions + Bark

环境变量：
    PUSH_CHANNEL=bark
    BARK_KEY=你的Bark Key

可选：
    BARK_SERVER=https://api.day.app

运行：
    python ai_news_push.py
"""

import os
import json
import datetime
import urllib.request
import urllib.parse


# ============================================================
# 基础配置
# ============================================================

UA = (
    "Mozilla/5.0 "
    "(Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0.0.0 "
    "Safari/537.36"
)

BASE = "https://aihot.virxact.com"


# ============================================================
# 配置
# ============================================================

DEFAULTS = {
    "PUSH_CHANNEL": "bark",

    # Bark
    "BARK_KEY": "",
    "BARK_SERVER": "",

    # Server 酱
    "SERVERCHAN_KEY": "",

    # Email
    "EMAIL_TO": "",
    "EMAIL_FROM": "",
    "EMAIL_PASS": "",
    "SMTP_HOST": "smtp.qq.com",
    "SMTP_PORT": "465",
}


# ============================================================
# 读取 .env
# ============================================================

def _load_dotenv(path=".env"):
    env = {}

    try:
        with open(path, encoding="utf-8") as f:

            for line in f:
                line = line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                k, v = line.split("=", 1)

                env[k.strip()] = (
                    v.strip()
                    .strip('"')
                    .strip("'")
                )

    except FileNotFoundError:
        pass

    return env


_DOTENV = _load_dotenv()


def cfg(name):
    """
    配置优先级：

    ① 系统环境变量
    ② .env
    ③ DEFAULTS
    """

    return (
        os.environ.get(name)
        or _DOTENV.get(name)
        or DEFAULTS.get(name, "")
    )


PUSH_CHANNEL = cfg("PUSH_CHANNEL")

BARK_KEY = cfg("BARK_KEY")
BARK_SERVER = cfg("BARK_SERVER")

SERVERCHAN_KEY = cfg("SERVERCHAN_KEY")

EMAIL_TO = cfg("EMAIL_TO")
EMAIL_FROM = cfg("EMAIL_FROM")
EMAIL_PASS = cfg("EMAIL_PASS")

SMTP_HOST = cfg("SMTP_HOST")
SMTP_PORT = int(cfg("SMTP_PORT") or "465")


# ============================================================
# 分类名称
# ============================================================

CAT_LABEL = {
    "ai-models": "🚀 模型发布",
    "ai-products": "🛠️ 产品动态",
    "industry": "🌐 行业动态",
    "paper": "📄 论文研究",
    "tip": "💡 技巧观点",
}


# ============================================================
# 网络请求
# ============================================================

def fetch(url):
    """
    GET JSON API
    """

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urllib.request.urlopen(req, timeout=30) as r:

        return json.loads(
            r.read().decode("utf-8")
        )


# ============================================================
# 获取日报
# ============================================================

def get_daily():
    """
    优先获取今日日报。

    如果今日日报还没有生成，
    自动尝试获取昨天的日报。
    """

    try:

        return fetch(
            f"{BASE}/api/public/daily"
        )

    except Exception:

        yesterday = (
            datetime.datetime.utcnow()
            - datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")

        return fetch(
            f"{BASE}/api/public/daily/{yesterday}"
        )


# ============================================================
# 工具：文字清理
# ============================================================

def clean_text(text):
    """
    清理多余空格和换行。
    """

    if not text:
        return ""

    text = str(text)

    text = text.replace("\r", "")
    text = text.replace("\n", " ")

    return " ".join(text.split())


# ============================================================
# 工具：截断文字
# ============================================================

def shorten(text, max_length=160):

    text = clean_text(text)

    if len(text) <= max_length:
        return text

    return text[:max_length] + "…"


# ============================================================
# 工具：生成数据条
# ============================================================

def make_bar(value, maximum, width=10):
    """
    把数字转换成：

    ████████░░

    这种手机通知里比较容易看的图形。
    """

    if maximum <= 0:
        return "░" * width

    ratio = value / maximum

    filled = round(ratio * width)

    filled = max(0, min(width, filled))

    return (
        "█" * filled
        + "░" * (width - filled)
    )


# ============================================================
# 工具：获取分类名称
# ============================================================

def get_category_name(section):

    # 如果 API 有 slug
    slug = section.get("slug")

    if slug in CAT_LABEL:
        return CAT_LABEL[slug]

    # 如果 API 没有 slug，就使用 label
    label = section.get("label")

    if label:
        return str(label)

    return "📰 其他"


# ============================================================
# 构建漂亮的 Bark 消息
# ============================================================

def build_text(daily):

    sections = daily.get("sections", [])

    flashes = daily.get("flashes") or []

    lead = daily.get("lead") or {}

    date = daily.get("date")

    lines = []

    # ========================================================
    # 统计所有新闻
    # ========================================================

    total_news = 0

    category_stats = []

    for section in sections:

        items = section.get("items", [])

        count = len(items)

        total_news += count

        category_name = get_category_name(section)

        category_stats.append(
            (category_name, count)
        )

    # 按新闻数量排序
    category_stats.sort(
        key=lambda x: x[1],
        reverse=True
    )

    # 最大分类数量
    max_count = max(
        [x[1] for x in category_stats],
        default=1
    )

    # ========================================================
    # 顶部
    # ========================================================

    lines.append("🤖 AI DAILY")

    if date:
        lines.append(
            f"{date} · 今日 AI 情报"
        )

    lines.append("━━━━━━━━━━━━")

    # ========================================================
    # 数据概览
    # ========================================================

    lines.append("📊 今日情报")

    lines.append(
        f"共 {total_news} 条 · 快讯 {len(flashes)} 条"
    )

    lines.append("")

    for category, count in category_stats:

        bar = make_bar(
            count,
            max_count
        )

        lines.append(
            f"{category:<10} {bar} {count}"
        )

    lines.append("")

    # ========================================================
    # TOP STORY
    # ========================================================

    if lead.get("title"):

        title = clean_text(
            lead.get("title")
        )

        paragraph = clean_text(
            lead.get("leadParagraph")
        )

        lines.append("🔥 今日头条")
        lines.append("━━━━━━━━━━━━")

        lines.append(title)

        if paragraph:

            lines.append("")

            lines.append(
                shorten(
                    paragraph,
                    220
                )
            )

        lines.append("")

    # ========================================================
    # 新闻分类
    # ========================================================

    # 每个分类最多显示 3 条
    MAX_ITEMS_PER_CATEGORY = 3

    for section in sections:

        items = section.get("items", [])

        if not items:
            continue

        category_name = get_category_name(section)

        lines.append(category_name)

        lines.append("━━━━━━━━━━━━")

        # 最多 3 条
        for index, item in enumerate(
            items[:MAX_ITEMS_PER_CATEGORY],
            start=1
        ):

            title = clean_text(
                item.get("title")
            )

            if not title:
                continue

            lines.append(
                f"{index:02d}  {title}"
            )

        # 如果超过3条
        if len(items) > MAX_ITEMS_PER_CATEGORY:

            remaining = (
                len(items)
                - MAX_ITEMS_PER_CATEGORY
            )

            lines.append(
                f"…还有 {remaining} 条"
            )

        lines.append("")

    # ========================================================
    # 快讯
    # ========================================================

    if flashes:

        lines.append("⚡ 30 秒快讯")
        lines.append("━━━━━━━━━━━━")

        # 最多 6 条
        for flash in flashes[:6]:

            title = clean_text(
                flash.get("title")
            )

            if not title:
                continue

            source = clean_text(
                flash.get("sourceName")
            )

            if source:

                lines.append(
                    f"• {title} · {source}"
                )

            else:

                lines.append(
                    f"• {title}"
                )

        lines.append("")

    # ========================================================
    # 底部
    # ========================================================

    lines.append("━━━━━━━━━━━━")

    lines.append(
        "💡 AI HOT · 每日 AI 情报"
    )

    lines.append(
        "来源：aihot.virxact.com"
    )

    return "\n".join(lines)


# ============================================================
# Bark
# ============================================================

def push_bark(
    title,
    body,
    url=None
):

    """
    Bark 推送。

    url：
        点击通知后打开的网页。
    """

    server = (
        BARK_SERVER
        or "https://api.day.app"
    ).rstrip("/")

    # Bark 通知不要太长
    MAX = 3000

    if len(body) > MAX:

        body = (
            body[:MAX]
            + "\n\n"
            + "…内容过长，已截断"
        )

    payload = {
        "device_key": BARK_KEY,
        "title": title,
        "body": body,

        # Bark 分组
        "group": "AI资讯",

        # 通知声音
        "sound": "minuet",
    }

    # 如果有文章 URL
    if url:

        payload["url"] = url

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{server}/push",
        data=data,
        method="POST",
        headers={
            "Content-Type":
                "application/json; charset=utf-8",

            "User-Agent": UA,
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=30
    ) as r:

        return r.read().decode("utf-8")


# ============================================================
# Server 酱
# ============================================================

def push_serverchan(
    title,
    body
):

    url = (
        f"https://sctapi.ftqq.com/"
        f"{SERVERCHAN_KEY}.send"
    )

    data = urllib.parse.urlencode(
        {
            "title": title,
            "desp": body,
        }
    ).encode()

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": UA
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=30
    ) as r:

        return r.read().decode()


# ============================================================
# Email
# ============================================================

def push_email(
    title,
    body
):

    import smtplib

    from email.mime.text import MIMEText

    msg = MIMEText(
        body,
        "plain",
        "utf-8"
    )

    msg["Subject"] = title
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT
    ) as s:

        s.login(
            EMAIL_FROM,
            EMAIL_PASS
        )

        s.sendmail(
            EMAIL_FROM,
            [EMAIL_TO],
            msg.as_string()
        )


# ============================================================
# 主程序
# ============================================================

def main():

    print("正在获取 AI HOT 日报...")

    # --------------------------------------------------------
    # 获取数据
    # --------------------------------------------------------

    daily = get_daily()

    print("日报获取成功")

    # --------------------------------------------------------
    # 生成推送内容
    # --------------------------------------------------------

    text = build_text(daily)

    date = daily.get("date")

    title = f"🤖 AI 资讯 · {date}"

    # --------------------------------------------------------
    # 获取头条 URL
    # --------------------------------------------------------

    lead = daily.get("lead") or {}

    lead_url = lead.get("sourceUrl")

    # --------------------------------------------------------
    # Bark
    # --------------------------------------------------------

    if PUSH_CHANNEL == "bark":

        if not BARK_KEY:

            raise ValueError(
                "请设置 BARK_KEY"
            )

        push_bark(
            title,
            text,
            lead_url
        )

        print(
            "✅ 已通过 Bark 推送到手机"
        )

    # --------------------------------------------------------
    # Server 酱
    # --------------------------------------------------------

    elif PUSH_CHANNEL == "serverchan":

        if not SERVERCHAN_KEY:

            raise ValueError(
                "请设置 SERVERCHAN_KEY"
            )

        push_serverchan(
            title,
            text
        )

        print(
            "✅ 已通过 Server 酱推送到微信"
        )

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    elif PUSH_CHANNEL == "email":

        if not EMAIL_TO:

            raise ValueError(
                "请设置 EMAIL_TO / EMAIL_PASS"
            )

        push_email(
            title,
            text
        )

        print(
            f"✅ 已发邮件到 {EMAIL_TO}"
        )

    # --------------------------------------------------------
    # 未知通道
    # --------------------------------------------------------

    else:

        print(
            "未知 PUSH_CHANNEL，"
            "仅打印预览："
        )

        print()
        print(text)


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    main()