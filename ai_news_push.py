# -*- coding: utf-8 -*-
"""经济新闻可视化早报

在 ai_news_push.py 的基础上增强：
- 抓取 RSS 经济新闻和 Yahoo Finance 市场数据
- 生成零依赖、响应式、可交互的 HTML 仪表盘
- 使用内联 SVG 绘制市场迷你走势图，不依赖第三方 Python 包
- 支持 Bark 推送；通知点击后打开 HTML 报告或新闻头条
- 支持 GitHub Actions，默认不需要安装第三方 Python 库

环境变量：
    BARK_KEY       Bark Key；为空时只生成报告，不推送
    BARK_SERVER    Bark 服务地址，默认 https://api.day.app
    REPORT_DIR     报告目录，默认 reports
    MAX_NEWS       每个新闻源最多读取条数，默认 8

示例：
    python economic_news_dashboard.py --demo
    python economic_news_dashboard.py --no-push
    BARK_KEY=xxx python economic_news_dashboard.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 EconomicNewsDashboard/1.0"
)
TIMEOUT = 20
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
BARK_KEY = os.getenv("BARK_KEY", "").strip()
BARK_SERVER = os.getenv("BARK_SERVER", "https://api.day.app").rstrip("/")
DEFAULT_REPORT_DIR = Path(os.getenv("REPORT_DIR", "reports"))
MAX_NEWS = max(3, int(os.getenv("MAX_NEWS", "8")))

RSS_SOURCES = [
    {"name": "BBC Business", "short": "BBC", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "全球经济", "accent": "cyan"},
    {"name": "CNBC Markets", "short": "CNBC", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "category": "全球市场", "accent": "violet"},
    {"name": "MarketWatch", "short": "MW", "url": "https://feeds.marketwatch.com/marketwatch/topstories/", "category": "市场动态", "accent": "amber"},
]

MARKETS = {
    "gold": {"name": "黄金", "symbol": "GC=F", "unit": "$", "decimals": 0, "icon": "◈", "color": "#f7c75c"},
    "oil": {"name": "原油", "symbol": "CL=F", "unit": "$", "decimals": 2, "icon": "◉", "color": "#ff8a65"},
    "sp500": {"name": "标普 500", "symbol": "^GSPC", "unit": "", "decimals": 0, "icon": "▦", "color": "#57d6a0"},
    "nasdaq": {"name": "纳斯达克", "symbol": "^IXIC", "unit": "", "decimals": 0, "icon": "⌁", "color": "#61a5ff"},
    "usd": {"name": "美元指数", "symbol": "DX-Y.NYB", "unit": "", "decimals": 2, "icon": "$", "color": "#be8cff"},
    "us10y": {"name": "美债 10Y", "symbol": "^TNX", "unit": "", "decimals": 2, "icon": "≋", "color": "#fb7da8"},
}

KEYWORDS = {
    "美联储": ("fed", "federal reserve", "fomc", "interest rate", "rate cut", "rate hike"),
    "通胀": ("inflation", "cpi", "ppi", "prices"),
    "就业": ("jobs", "employment", "unemployment", "payroll"),
    "增长": ("gdp", "growth", "economy", "recession"),
    "贸易": ("tariff", "trade", "export", "import"),
    "中国": ("china", "chinese", "beijing"),
    "黄金": ("gold", "bullion"),
    "原油": ("oil", "crude", "opec"),
    "债券": ("bond", "treasury", "yield"),
}
POSITIVE = ("rally", "gain", "gains", "surge", "rise", "rises", "higher", "beat", "strong", "optimism", "增长", "上涨")
NEGATIVE = ("fall", "falls", "drop", "drops", "lower", "loss", "losses", "risk", "crisis", "recession", "weak", "decline", "下跌", "风险")


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def shorten(text: str, length: int = 180) -> str:
    text = clean_text(text)
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = dt.datetime.strptime(value[:25], "%a, %d %b %Y %H:%M:%S")
        return parsed.strftime("%m/%d %H:%M")
    except ValueError:
        return value[:16]


def score_news(item: dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    score = 0
    for words in KEYWORDS.values():
        score += sum(2 for word in words if word in text)
    score += 3 if item.get("source") in {"BBC", "CNBC"} else 0
    return score


def sentiment_for(text: str) -> str:
    lowered = text.lower()
    positive = sum(word in lowered for word in POSITIVE)
    negative = sum(word in lowered for word in NEGATIVE)
    if positive > negative:
        return "偏积极"
    if negative > positive:
        return "偏谨慎"
    return "中性"


def parse_rss(source: dict[str, str]) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(request_bytes(source["url"]))
    except Exception as exc:
        print(f"[WARN] {source['name']} 获取失败：{exc}", file=sys.stderr)
        return []

    items: list[dict[str, Any]] = []
    nodes = root.findall(".//item") or root.findall(".//{*}entry")
    for node in nodes[:MAX_NEWS]:
        def get_text(*names: str) -> str:
            for name in names:
                child = node.find(name)
                if child is None:
                    child = node.find(f"{{*}}{name}")
                if child is not None and child.text:
                    return clean_text(child.text)
            return ""

        link = get_text("link")
        if not link:
            link_node = node.find("{*}link")
            link = (link_node.get("href", "") if link_node is not None else "")
        title = get_text("title")
        if not title:
            continue
        description = get_text("description", "summary", "content")
        published = get_text("pubDate", "published", "updated")
        item = {
            "title": title,
            "description": shorten(description),
            "url": link,
            "source": source["short"],
            "source_name": source["name"],
            "category": source["category"],
            "accent": source["accent"],
            "published": parse_date(published),
        }
        item["score"] = score_news(item)
        item["sentiment"] = sentiment_for(f"{title} {description}")
        items.append(item)
    return items


def deduplicate_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda value: value["score"], reverse=True):
        key = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", item["title"].lower())[:80]
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def get_market(config: dict[str, Any]) -> dict[str, Any] | None:
    symbol = urllib.parse.quote(config["symbol"], safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    try:
        data = request_json(url)
        result = data["chart"]["result"][0]
        closes = [value for value in result["indicators"]["quote"][0]["close"] if value is not None]
        timestamps = result.get("timestamp", [])
        if not closes:
            return None
        current = float(closes[-1])
        previous = float(closes[-2]) if len(closes) > 1 else current
        change = ((current - previous) / previous * 100) if previous else 0
        return {**config, "price": current, "change": change, "history": [float(v) for v in closes[-14:]], "updated": timestamps[-1] if timestamps else None}
    except Exception as exc:
        print(f"[WARN] {config['name']} 获取失败：{exc}", file=sys.stderr)
        return None


def get_markets() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, config in MARKETS.items():
        value = get_market(config)
        if value:
            result[key] = value
    return result


def demo_data() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    titles = [
        ("Markets weigh rate-cut expectations as investors parse fresh inflation signals", "CNBC", "全球市场", "偏谨慎"),
        ("Global growth outlook gets a lift from resilient consumer demand", "BBC", "全球经济", "偏积极"),
        ("Oil prices steady as traders watch supply and geopolitical risks", "MW", "市场动态", "中性"),
        ("Treasury yields move higher ahead of central bank remarks", "CNBC", "全球市场", "偏谨慎"),
        ("Gold holds firm as investors seek protection against uncertainty", "BBC", "全球经济", "偏积极"),
        ("China data keeps Asia markets focused on industrial recovery", "MW", "市场动态", "中性"),
    ]
    news = []
    for index, (title, source, category, sentiment) in enumerate(titles):
        item = {"title": title, "description": "示例数据：使用 --demo 可预览报告样式，不会访问网络或推送。", "url": "https://example.com", "source": source, "source_name": source, "category": category, "accent": ["cyan", "violet", "amber"][index % 3], "published": f"09/{11 - index:02d} 08:{20 + index:02d}", "score": 12 - index, "sentiment": sentiment}
        news.append(item)
    markets = {}
    for index, (key, config) in enumerate(MARKETS.items()):
        base = [2655, 68.42, 5485, 17560, 101.2, 4.08][index]
        change = [0.78, -1.12, 0.42, 0.66, -0.21, 0.08][index]
        history = [base * (1 + math.sin(i / 2.2 + index) * 0.012 + i * change / 100 / 14) for i in range(14)]
        markets[key] = {**config, "price": base, "change": change, "history": history, "updated": None}
    return news, markets


def format_price(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}"


def sparkline(history: list[float], color: str) -> str:
    if len(history) < 2:
        return ""
    width, height, pad = 180, 44, 3
    lo, hi = min(history), max(history)
    span = hi - lo or 1
    points = []
    for index, value in enumerate(history):
        x = pad + index * (width - pad * 2) / (len(history) - 1)
        y = height - pad - (value - lo) / span * (height - pad * 2)
        points.append(f"{x:.1f},{y:.1f}")
    area = f"{pad},{height - pad} " + " ".join(points) + f" {width - pad},{height - pad}"
    return f'<svg class="sparkline" viewBox="0 0 {width} {height}" role="img" aria-label="价格走势"><polygon points="{area}" fill="{color}" opacity=".12"/><polyline points="{' '.join(points)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def badge(text: str, class_name: str = "") -> str:
    return f'<span class="badge {class_name}">{html.escape(text)}</span>'


def build_market_cards(markets: dict[str, dict[str, Any]]) -> str:
    cards = []
    for data in markets.values():
        change = float(data["change"])
        trend_class = "up" if change >= 0 else "down"
        arrow = "↗" if change >= 0 else "↘"
        cards.append(f"""
        <article class="market-card" style="--accent:{data['color']}">
          <div class="market-top"><span class="market-icon">{html.escape(data['icon'])}</span><span class="market-name">{html.escape(data['name'])}</span><span class="market-symbol">{html.escape(data['symbol'])}</span></div>
          <div class="market-main"><strong>{html.escape(data['unit'])}{format_price(data['price'], data['decimals'])}</strong><span class="change {trend_class}">{arrow} {change:+.2f}%</span></div>
          {sparkline(data.get('history', []), data['color'])}
        </article>""")
    return "\n".join(cards) or '<div class="empty">市场数据暂时不可用</div>'


def build_category_chart(news: list[dict[str, Any]]) -> str:
    counts = Counter(item["category"] for item in news)
    palette = ["#63d8c2", "#a98bff", "#ffca62", "#ff7da9", "#69a8ff"]
    total = max(sum(counts.values()), 1)
    angle = 0.0
    stops = []
    legend = []
    for index, (name, count) in enumerate(counts.most_common()):
        end = angle + count / total * 360
        stops.append(f"{palette[index % len(palette)]} {angle:.1f}deg {end:.1f}deg")
        legend.append(f'<li><i style="background:{palette[index % len(palette)]}"></i>{html.escape(name)} <b>{count}</b></li>')
        angle = end
    gradient = ", ".join(stops) or "#26324a 0 360deg"
    return f'<div class="donut" style="background:conic-gradient({gradient})"><div>{total}<small>条新闻</small></div></div><ul class="legend">{"".join(legend)}</ul>'


def keyword_chips(news: list[dict[str, Any]]) -> str:
    joined = " ".join(f"{item['title']} {item['description']}".lower() for item in news)
    matched = [(name, sum(any(word in joined for word in words) for _ in [0])) for name, words in KEYWORDS.items()]
    matched = [(name, count) for name, count in matched if count]
    matched.sort(key=lambda pair: pair[1], reverse=True)
    return "".join(f'<span class="topic-chip">{html.escape(name)}</span>' for name, _ in matched[:8]) or '<span class="muted">暂无明显主题</span>'


def build_news_list(news: list[dict[str, Any]]) -> str:
    blocks = []
    for index, item in enumerate(news[:18], start=1):
        sentiment_class = {"偏积极": "positive", "偏谨慎": "negative", "中性": "neutral"}.get(item["sentiment"], "neutral")
        link = html.escape(item.get("url") or "#", quote=True)
        blocks.append(f"""
        <a class="news-item" href="{link}" target="_blank" rel="noopener">
          <div class="news-rank">{index:02d}</div>
          <div class="news-copy"><div class="news-meta">{badge(item['source'], item.get('accent', 'cyan'))} <span>{html.escape(item['category'])}</span><span>{html.escape(item.get('published', ''))}</span></div><h3>{html.escape(item['title'])}</h3><p>{html.escape(item.get('description', ''))}</p></div>
          <div class="sentiment {sentiment_class}">{html.escape(item['sentiment'])}</div>
        </a>""")
    return "\n".join(blocks) or '<div class="empty">没有抓到新闻，请检查网络或 RSS 源。</div>'


def build_bark_body(news: list[dict[str, Any]], markets: dict[str, dict[str, Any]], report_url: str) -> str:
    lines = ["📡 今日市场快照"]
    for key in ("gold", "oil", "sp500", "nasdaq"):
        data = markets.get(key)
        if data:
            lines.append(f"{data['name']} {data['price']:,.{data['decimals']}f} ({data['change']:+.2f}%)")
    lines.extend(["", "📰 重点新闻"])
    for item in news[:3]:
        lines.append(f"· {shorten(item['title'], 68)}")
    lines.extend(["", f"📊 查看可视化报告：{report_url}"])
    return "\n".join(lines)


def render_html(news: list[dict[str, Any]], markets: dict[str, dict[str, Any]], generated_at: str, report_title: str) -> str:
    positive = sum(item["sentiment"] == "偏积极" for item in news)
    negative = sum(item["sentiment"] == "偏谨慎" for item in news)
    neutral = len(news) - positive - negative
    top_story = news[0] if news else None
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(report_title)}</title>
<style>
:root{{--bg:#0a0d16;--panel:#111827;--panel2:#151e30;--line:#26324a;--text:#f3f6fb;--muted:#93a0b8;--cyan:#63d8c2;--violet:#a98bff;--amber:#ffca62;--pink:#ff7da9;--shadow:0 24px 60px rgba(0,0,0,.28)}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 80% -15%,#243b61 0,transparent 35%),radial-gradient(circle at -10% 30%,#183e46 0,transparent 28%),var(--bg);color:var(--text);font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.5}}a{{color:inherit;text-decoration:none}}.shell{{max-width:1440px;margin:0 auto;padding:30px 28px 52px}}.header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:28px}}.eyebrow{{color:var(--cyan);font-size:12px;letter-spacing:.18em;text-transform:uppercase;font-weight:800}}h1{{font-size:clamp(30px,5vw,64px);line-height:1.05;margin:9px 0 12px;letter-spacing:-.06em}}.subtitle{{color:var(--muted);max-width:720px;margin:0;font-size:15px}}.stamp{{border:1px solid var(--line);background:rgba(17,24,39,.7);border-radius:16px;padding:12px 16px;color:var(--muted);font-size:12px;text-align:right;white-space:nowrap}}.stamp strong{{display:block;color:var(--text);font-size:17px;margin-top:2px}}.hero{{display:grid;grid-template-columns:1.35fr .65fr;gap:18px;margin-bottom:18px}}.hero-card,.panel,.market-card{{background:linear-gradient(145deg,rgba(21,30,48,.94),rgba(15,21,34,.94));border:1px solid rgba(132,158,208,.18);box-shadow:var(--shadow);border-radius:22px}}.hero-card{{padding:28px;min-height:190px;position:relative;overflow:hidden}}.hero-card:after{{content:"";position:absolute;width:280px;height:280px;border-radius:50%;right:-100px;top:-140px;background:radial-gradient(circle,rgba(99,216,194,.25),transparent 68%)}}.hero-label{{font-size:12px;color:var(--amber);font-weight:800;letter-spacing:.12em}}.hero-title{{max-width:780px;font-size:clamp(21px,3vw,34px);line-height:1.25;margin:13px 0 12px;letter-spacing:-.03em}}.hero-desc{{max-width:760px;color:var(--muted);font-size:14px}}.hero-link{{display:inline-flex;margin-top:18px;color:var(--cyan);font-size:13px;font-weight:700}}.pulse{{padding:24px;display:flex;flex-direction:column;justify-content:space-between}}.pulse h2,.panel h2{{font-size:15px;margin:0 0 15px}}.pulse-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}.pulse-stat{{border:1px solid var(--line);border-radius:14px;padding:12px 8px;text-align:center;background:rgba(8,12,22,.3)}}.pulse-stat b{{display:block;font-size:24px;line-height:1.1}}.pulse-stat span{{color:var(--muted);font-size:11px}}.up{{color:var(--cyan)}}.down{{color:var(--pink)}}.neutral{{color:var(--amber)}}.section-title{{display:flex;justify-content:space-between;align-items:center;margin:30px 0 13px}}.section-title h2{{margin:0;font-size:20px;letter-spacing:-.03em}}.section-title span{{color:var(--muted);font-size:12px}}.market-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}}.market-card{{padding:16px 15px 10px;overflow:hidden;border-top:2px solid var(--accent)}}.market-top{{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:12px}}.market-icon{{color:var(--accent);font-size:17px;font-weight:800}}.market-symbol{{margin-left:auto;opacity:.6;font-size:10px}}.market-main{{display:flex;align-items:baseline;justify-content:space-between;gap:4px;margin-top:14px}}.market-main strong{{font-size:20px;letter-spacing:-.04em}}.change{{font-size:12px;font-weight:800;white-space:nowrap}}.sparkline{{display:block;width:100%;height:44px;margin-top:8px}}.dashboard{{display:grid;grid-template-columns:1.5fr .5fr;gap:18px;align-items:start}}.panel{{padding:22px}}.news-list{{display:grid;gap:2px}}.news-item{{display:grid;grid-template-columns:44px 1fr auto;gap:13px;padding:17px 4px;border-bottom:1px solid rgba(132,158,208,.13);transition:.18s ease}}.news-item:hover{{background:rgba(99,216,194,.05);padding-left:10px;padding-right:10px;border-radius:12px}}.news-rank{{color:#53617d;font-size:23px;font-weight:800;letter-spacing:-.08em}}.news-meta{{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:11px;margin-bottom:6px;flex-wrap:wrap}}.badge{{border-radius:999px;border:1px solid rgba(99,216,194,.4);padding:3px 7px;color:var(--cyan);font-size:10px;font-weight:800;letter-spacing:.04em}}.badge.violet{{color:var(--violet);border-color:rgba(169,139,255,.4)}}.badge.amber{{color:var(--amber);border-color:rgba(255,202,98,.4)}}.news-copy h3{{margin:0;font-size:15px;line-height:1.45;font-weight:750}}.news-copy p{{color:var(--muted);font-size:12px;margin:6px 0 0;line-height:1.5}}.sentiment{{font-size:11px;white-space:nowrap;padding-top:25px;font-weight:800}}.positive{{color:var(--cyan)}}.negative{{color:var(--pink)}}.legend{{list-style:none;padding:0;margin:18px 0 0;display:grid;gap:10px}}.legend li{{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}}.legend i{{display:inline-block;width:8px;height:8px;border-radius:50%}}.legend b{{margin-left:auto;color:var(--text)}}.donut{{width:176px;height:176px;border-radius:50%;display:grid;place-items:center;margin:10px auto 18px}}.donut>div{{width:114px;height:114px;border-radius:50%;background:var(--panel);display:grid;place-content:center;text-align:center;font-size:31px;font-weight:800;line-height:1}}.donut small{{display:block;color:var(--muted);font-size:11px;font-weight:500;margin-top:6px}}.topics{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}.topic-chip{{background:rgba(99,216,194,.1);border:1px solid rgba(99,216,194,.28);padding:6px 9px;border-radius:999px;color:var(--cyan);font-size:12px}}.muted,.empty{{color:var(--muted)}}.empty{{padding:25px;text-align:center}}.footer{{display:flex;justify-content:space-between;gap:12px;margin-top:25px;color:#65718a;font-size:11px;border-top:1px solid var(--line);padding-top:16px}}@media(max-width:1100px){{.market-grid{{grid-template-columns:repeat(3,1fr)}}.dashboard,.hero{{grid-template-columns:1fr}}}}@media(max-width:640px){{.shell{{padding:20px 14px 35px}}.header{{align-items:flex-start;flex-direction:column}}.stamp{{text-align:left}}.market-grid{{grid-template-columns:repeat(2,1fr);gap:9px}}.market-card{{padding:13px 11px}}.market-main{{display:block}}.change{{display:block;margin-top:4px}}.news-item{{grid-template-columns:30px 1fr}}.sentiment{{display:none}}.panel,.hero-card,.pulse{{padding:17px;border-radius:17px}}.footer{{display:block}}.footer span{{display:block;margin-bottom:5px}}}}
</style></head><body><main class="shell">
<header class="header"><div><div class="eyebrow">ECONOMIC SIGNALS / DAILY BRIEF</div><h1>全球经济脉搏</h1><p class="subtitle">把新闻、价格与主题放在同一张桌面上。先看市场温度，再读影响资产价格的关键叙事。</p></div><div class="stamp">报告生成时间<strong>{html.escape(generated_at)}</strong>纯 Python · 无第三方依赖</div></header>
<section class="hero"><article class="hero-card"><div class="hero-label">TOP SIGNAL · 今日最值得先读</div><div class="hero-title">{html.escape(top_story['title'] if top_story else '暂无头条，稍后再试')}</div><div class="hero-desc">{html.escape(top_story.get('description','') if top_story else '当前没有可展示的新闻摘要。')}</div>{f'<a class="hero-link" href="{html.escape(top_story.get("url") or "#", quote=True)}" target="_blank">打开原文 ↗</a>' if top_story else ''}</article><article class="panel pulse"><h2>新闻情绪温度</h2><div class="pulse-grid"><div class="pulse-stat"><b class="up">{positive}</b><span>偏积极</span></div><div class="pulse-stat"><b class="neutral">{neutral}</b><span>中性</span></div><div class="pulse-stat"><b class="down">{negative}</b><span>偏谨慎</span></div></div><div class="topics"><span class="muted">今日主题</span>{keyword_chips(news)}</div></article></section>
<div class="section-title"><h2>市场快照</h2><span>上一交易日收盘变动</span></div><section class="market-grid">{build_market_cards(markets)}</section>
<div class="section-title"><h2>新闻雷达</h2><span>按经济相关性排序 · 点击标题打开原文</span></div><section class="dashboard"><article class="panel"><div class="news-list">{build_news_list(news)}</div></article><aside class="panel"><h2>来源分布</h2>{build_category_chart(news)}<div style="border-top:1px solid var(--line);margin-top:22px;padding-top:18px"><h2>阅读提示</h2><p class="muted" style="font-size:12px;margin:0">情绪标签由关键词规则生成，仅用于快速扫读，不代表投资建议。价格数据来自公开市场接口，可能存在延迟。</p></div></aside></section>
<footer class="footer"><span>数据来源：公开 RSS 新闻源与 Yahoo Finance Chart API</span><span>Generated by economic_news_dashboard.py</span></footer></main></body></html>'''


def write_report(html_text: str, report_dir: Path, now: dt.datetime) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"economic_news_{now.strftime('%Y-%m-%d')}.html"
    report_path.write_text(html_text, encoding="utf-8")
    latest = report_dir / "latest.html"
    latest.write_text(html_text, encoding="utf-8")
    return report_path


def push_bark(title: str, body: str, url: str = "") -> str:
    if not BARK_KEY:
        return "未设置 BARK_KEY，跳过 Bark 推送。"
    payload: dict[str, Any] = {"device_key": BARK_KEY, "title": title, "body": body, "group": "经济早报", "sound": "minuet", "level": "active"}
    if url and not url.startswith("file:"):
        payload["url"] = url
    request = urllib.request.Request(f"{BARK_SERVER}/push", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成可视化经济新闻早报")
    parser.add_argument("--demo", action="store_true", help="使用内置示例数据，预览页面样式，不访问网络")
    parser.add_argument("--no-push", action="store_true", help="只生成 HTML，不推送 Bark")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_DIR, help="报告输出目录")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = dt.datetime.now()
    print("📡 正在生成经济新闻可视化早报……")
    if args.demo:
        news, markets = demo_data()
    else:
        markets = get_markets()
        news = deduplicate_news([item for source in RSS_SOURCES for item in parse_rss(source)])
        news = news[:18]
    generated_at = now.strftime("%Y-%m-%d %H:%M")
    report_title = f"全球经济脉搏 · {now.strftime('%Y-%m-%d')}"
    report_html = render_html(news, markets, generated_at, report_title)
    report_path = write_report(report_html, args.output, now)
    print(f"✅ 报告已生成：{report_path.resolve()}")
    print(f"   新闻 {len(news)} 条 · 市场 {len(markets)} 项")

    if not args.no_push and not args.demo:
        report_url = os.getenv("REPORT_URL", "")
        top_url = news[0].get("url", "") if news else ""
        push_target = report_url or top_url
        try:
            result = push_bark(f"📈 经济早报 · {now.strftime('%m/%d')}", build_bark_body(news, markets, report_url or str(report_path.resolve())), push_target)
            print(f"✅ Bark 推送完成：{shorten(result, 120)}")
        except Exception as exc:
            print(f"[WARN] Bark 推送失败：{exc}", file=sys.stderr)
    elif args.demo:
        print("ℹ️ demo 模式：未执行 Bark 推送。")
    else:
        print("ℹ️ --no-push：未执行 Bark 推送。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


