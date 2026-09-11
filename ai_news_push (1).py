# -*- coding: utf-8 -*-
"""
AI 资讯自动推送到手机 —— 基于 aihot.virxact.com 公开接口
=========================================================
功能：每天定时拉取 AI HOT 精选 / 日报，整理后推送到你的手机。
支持三个通道（通过环境变量切换）：
  - bark      : iPhone 免费推送，需安装 Bark App
  - serverchan: 推送到微信（Server 酱 / PushPlus），需微信扫码
  - email     : 发到自己邮箱（手机收邮件通知）

用法：
  1. pip install requests
  2. 配置环境变量（见下方 CONFIG），例如：
       export PUSH_CHANNEL=bark
       export BARK_KEY=你Bark里的key
  3. python3 ai_news_push.py
  4. 想每天自动跑：用 cron / GitHub Actions / 云函数定时执行（见仓库 README）

数据接口：https://aihot.virxact.com （匿名可访，无需 token）
"""
import os, json, datetime, urllib.request, urllib.parse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
BASE = "https://aihot.virxact.com"

# ---------------- 配置 ----------------
# 三种填法都行，优先级：① 环境变量 ② 同目录 .env 文件 ③ 下面的 DEFAULTS 直接填
# 不想碰命令行？最省事：把下面 DEFAULTS 里的 BARK_KEY 填上，保存就能跑。
DEFAULTS = {
    "PUSH_CHANNEL": "bark",        # bark / serverchan / email
    "BARK_KEY": "",                # ← 填你的 Bark key（App 首页地址末尾那串）
    "BARK_SERVER": "",             # 自建时填你的域名，留空用官方公服 api.day.app
    "SERVERCHAN_KEY": "",          # Server 酱 / PushPlus token（用微信通道时填）
    "EMAIL_TO": "",                # 接收邮箱
    "EMAIL_FROM": "",
    "EMAIL_PASS": "",
    "SMTP_HOST": "smtp.qq.com",
    "SMTP_PORT": "465",
}

def _load_dotenv(path=".env"):
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

_DOTENV = _load_dotenv()

def cfg(name):
    return os.environ.get(name) or _DOTENV.get(name) or DEFAULTS.get(name, "")

PUSH_CHANNEL   = cfg("PUSH_CHANNEL")
BARK_KEY       = cfg("BARK_KEY")
BARK_SERVER    = cfg("BARK_SERVER")
SERVERCHAN_KEY = cfg("SERVERCHAN_KEY")
EMAIL_TO       = cfg("EMAIL_TO")
EMAIL_FROM     = cfg("EMAIL_FROM")
EMAIL_PASS     = cfg("EMAIL_PASS")
SMTP_HOST      = cfg("SMTP_HOST")
SMTP_PORT      = int(cfg("SMTP_PORT") or "465")

CAT_LABEL = {
    "ai-models": "🚀 模型发布/更新", "ai-products": "🛠️ 产品发布/更新",
    "industry": "🌐 行业动态", "paper": "📄 论文研究", "tip": "💡 技巧与观点",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_daily():
    """优先今日日报，没有就退回昨日（北京时间 08:00 才生成今日）。"""
    try:
        return fetch(f"{BASE}/api/public/daily")
    except Exception:
        y = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        return fetch(f"{BASE}/api/public/daily/{y}")


def build_text(daily):
    lines = [f"🤖 AI HOT 日报 · {daily.get('date')}", ""]
    lead = daily.get("lead") or {}
    if lead.get("title"):
        lines.append(f"【今日头条】{lead['title']}")
        if lead.get("leadParagraph"):
            lines.append(lead["leadParagraph"][:200])
        lines.append("")
    for sec in daily.get("sections", []):
        lines.append(f"## {sec.get('label')}")
        for it in sec.get("items", []):
            lines.append(f"• {it.get('title')}")
            if it.get("sourceUrl"):
                lines.append(f"  {it['sourceUrl']}")
        lines.append("")
    flashes = daily.get("flashes") or []
    if flashes:
        lines.append("## ⚡ 快讯")
        for f in flashes:
            lines.append(f"• {f.get('title')}（{f.get('sourceName')}）")
    lines.append("")
    lines.append("数据来源：aihot.virxact.com")
    return "\n".join(lines)


def push_bark(title, body):
    # BARK_SERVER 留空 = 官方公服 api.day.app（免费）；自建时填自己的域名
    server = (BARK_SERVER or "https://api.day.app").rstrip("/")
    # 用 POST 把内容放请求体：避免内容太长导致 URL 超限（HTTP 431）。
    # Bark 通知本身约 4KB 上限，超长截断并提示去站点看完整版。
    MAX = 3000
    if len(body) > MAX:
        body = body[:MAX] + "\n…（内容过长已截断，完整版见 aihot.virxact.com）"
    payload = json.dumps({
        "device_key": BARK_KEY, "title": title, "body": body, "group": "AI资讯",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{server}/push", data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def push_serverchan(title, body):
    # 默认 Server 酱；PushPlus 把地址换成 https://www.pushplus.plus/send 即可
    url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
    data = urllib.parse.urlencode({"title": title, "desp": body}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def push_email(title, body):
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())


def main():
    daily = get_daily()
    text = build_text(daily)
    title = f"AI 资讯 · {daily.get('date')}"
    if PUSH_CHANNEL == "bark":
        assert BARK_KEY, "请设置环境变量 BARK_KEY"
        push_bark(title, text)
        print("✅ 已通过 Bark 推送到手机")
    elif PUSH_CHANNEL == "serverchan":
        assert SERVERCHAN_KEY, "请设置环境变量 SERVERCHAN_KEY"
        push_serverchan(title, text)
        print("✅ 已通过 Server 酱推送到微信")
    elif PUSH_CHANNEL == "email":
        assert EMAIL_TO, "请设置环境变量 EMAIL_TO / EMAIL_PASS"
        push_email(title, text)
        print(f"✅ 已发邮件到 {EMAIL_TO}")
    else:
        print("未知通道，仅打印预览：\n")
        print(text)


if __name__ == "__main__":
    main()
