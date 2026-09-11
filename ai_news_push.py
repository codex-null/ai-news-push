# -*- coding: utf-8 -*-

"""
每日经济早报
==============================

功能：

1. 获取全球经济 / 财经新闻
2. 获取黄金、原油、美股、美元指数等市场数据
3. 自动计算涨跌幅
4. 生成适合手机阅读的经济早报
5. 通过 Bark 推送到 iPhone
6. 点击通知可以打开当天头条
7. 支持 GitHub Actions 定时运行

不需要额外安装第三方 Python 库。

只需要设置：

BARK_KEY=你的Bark Key

推荐：

GitHub Actions + Bark
"""


import os
import json
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


# ============================================================
# 基础配置
# ============================================================

UA = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ============================================================
# Bark
# ============================================================

BARK_KEY = os.environ.get("BARK_KEY", "")

BARK_SERVER = os.environ.get(
    "BARK_SERVER",
    "https://api.day.app"
).rstrip("/")


# ============================================================
# 新闻源
# ============================================================

RSS_SOURCES = [

    # BBC Business
    {
        "name": "BBC",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "category": "全球经济",
    },

    # CNBC Markets
    {
        "name": "CNBC",
        "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "category": "全球市场",
    },

]


# ============================================================
# 市场数据
# Yahoo Finance Chart API
# ============================================================

MARKETS = {

    "gold": {
        "name": "黄金",
        "symbol": "GC=F",
        "unit": "$",
        "decimals": 0,
    },

    "oil": {
        "name": "原油",
        "symbol": "CL=F",
        "unit": "$",
        "decimals": 2,
    },

    "sp500": {
        "name": "标普500",
        "symbol": "^GSPC",
        "unit": "",
        "decimals": 0,
    },

    "nasdaq": {
        "name": "纳指",
        "symbol": "^IXIC",
        "unit": "",
        "decimals": 0,
    },

    "usd": {
        "name": "美元指数",
        "symbol": "DX-Y.NYB",
        "unit": "",
        "decimals": 2,
    },

    "us10y": {
        "name": "美债10Y",
        "symbol": "^TNX",
        "unit": "",
        "decimals": 2,
    },

}


# ============================================================
# 网络请求
# ============================================================

def fetch_json(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def fetch_text(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        return response.read()


# ============================================================
# Yahoo Finance
# ============================================================

def get_market(symbol):

    """
    获取最近几个交易日的数据。

    返回：

    {
        price: 当前价格,
        change: 涨跌幅
    }
    """

    encoded_symbol = urllib.parse.quote(
        symbol,
        safe=""
    )

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{encoded_symbol}"
        "?range=5d"
        "&interval=1d"
    )

    try:

        data = fetch_json(url)

        result = data["chart"]["result"][0]

        quote = result["indicators"]["quote"][0]

        closes = [
            x
            for x in quote["close"]
            if x is not None
        ]

        if not closes:

            return None

        current = closes[-1]

        if len(closes) >= 2:

            previous = closes[-2]

            change = (
                (current - previous)
                / previous
                * 100
            )

        else:

            change = 0

        return {
            "price": current,
            "change": change
        }

    except Exception as e:

        print(
            f"获取 {symbol} 失败：{e}"
        )

        return None


# ============================================================
# 获取所有市场数据
# ============================================================

def get_markets():

    result = {}

    for key, config in MARKETS.items():

        data = get_market(
            config["symbol"]
        )

        if data is not None:

            result[key] = {
                **config,
                **data
            }

    return result


# ============================================================
# RSS 新闻
# ============================================================

def parse_rss(source):

    """
    获取 RSS 新闻。

    尽可能兼容不同 RSS 格式。
    """

    news = []

    try:

        content = fetch_text(
            source["url"]
        )

        root = ET.fromstring(content)

        items = root.findall(".//item")

        for item in items[:10]:

            title_node = item.find("title")
            link_node = item.find("link")
            description_node = item.find(
                "description"
            )

            title = (
                title_node.text
                if title_node is not None
                else ""
            )

            link = (
                link_node.text
                if link_node is not None
                else ""
            )

            description = (
                description_node.text
                if description_node is not None
                else ""
            )

            if not title:

                continue

            news.append({
                "title": clean_text(title),
                "description": clean_text(
                    description
                ),
                "url": link or "",
                "source": source["name"],
                "category": source["category"],
            })

    except Exception as e:

        print(
            f"RSS 获取失败："
            f"{source['name']} - {e}"
        )

    return news


# ============================================================
# 获取新闻
# ============================================================

def get_news():

    all_news = []

    for source in RSS_SOURCES:

        result = parse_rss(source)

        all_news.extend(result)

    return all_news


# ============================================================
# 文本处理
# ============================================================

def clean_text(text):

    if not text:

        return ""

    text = str(text)

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    return " ".join(
        text.split()
    )


def shorten(
    text,
    length=150
):

    text = clean_text(text)

    if len(text) <= length:

        return text

    return text[:length] + "…"


# ============================================================
# 判断新闻重要程度
# ============================================================

def score_news(news):

    """
    根据经济关键词简单判断重要程度。

    不是 AI 摘要，
    只是避免把普通新闻放到最前面。
    """

    title = (
        news["title"]
        + " "
        + news.get(
            "description",
            ""
        )
    ).lower()

    keywords = {

        # 利率
        "fed": 8,
        "federal reserve": 8,
        "interest rate": 8,
        "rate cut": 10,
        "rate hike": 10,

        # 通胀
        "inflation": 9,
        "cpi": 9,
        "ppi": 7,

        # 就业
        "jobs": 8,
        "employment": 8,
        "unemployment": 8,

        # 经济
        "economy": 6,
        "gdp": 9,
        "recession": 10,

        # 市场
        "stocks": 5,
        "market": 4,
        "bond": 6,

        # 黄金 / 原油
        "gold": 6,
        "oil": 6,
        "crude": 6,

        # 中国
        "china": 7,
        "chinese": 7,

        # 贸易
        "tariff": 9,
        "trade": 7,
    }

    score = 0

    for keyword, weight in keywords.items():

        if keyword in title:

            score += weight

    return score


# ============================================================
# 新闻去重
# ============================================================

def deduplicate_news(news):

    seen = set()

    result = []

    for item in news:

        key = item["title"].lower()

        if key in seen:

            continue

        seen.add(key)

        result.append(item)

    return result


# ============================================================
# 市场数据格式化
# ============================================================

def format_market(data):

    price = data["price"]

    change = data["change"]

    decimals = data["decimals"]

    unit = data["unit"]

    if change > 0:

        arrow = "↑"

    elif change < 0:

        arrow = "↓"

    else:

        arrow = "→"

    if decimals == 0:

        price_text = f"{unit}{price:,.0f}"

    else:

        price_text = (
            f"{unit}{price:,.{decimals}f}"
        )

    return (
        f"{price_text} "
        f"{arrow} "
        f"{change:+.2f}%"
    )


# ============================================================
# 市场状态描述
# ============================================================

def market_comment(markets):

    comments = []

    if "gold" in markets:

        change = markets["gold"]["change"]

        if change > 1:

            comments.append(
                "黄金今天表现偏强"
            )

        elif change < -1:

            comments.append(
                "黄金今天明显走弱"
            )

    if "oil" in markets:

        change = markets["oil"]["change"]

        if change > 1:

            comments.append(
                "原油走高"
            )

        elif change < -1:

            comments.append(
                "原油承压"
            )

    if "sp500" in markets:

        change = markets["sp500"]["change"]

        if change > 0.5:

            comments.append(
                "美股风险偏好较强"
            )

        elif change < -0.5:

            comments.append(
                "美股风险偏好偏弱"
            )

    if "us10y" in markets:

        change = markets["us10y"]["change"]

        if change > 1:

            comments.append(
                "美债收益率上行"
            )

        elif change < -1:

            comments.append(
                "美债收益率回落"
            )

    if not comments:

        return (
            "今天市场整体没有特别明显的单边行情，"
            "重点还是看利率、美元和风险资产之间的变化。"
        )

    return (
        "；".join(comments)
        + "。"
    )


# ============================================================
# 生成新闻段落
# ============================================================

def build_news_section(
    news,
    title,
    limit=3
):

    lines = []

    selected = news[:limit]

    if not selected:

        return lines

    lines.append(title)
    lines.append("")
    lines.append("")

    for index, item in enumerate(
        selected,
        start=1
    ):

        lines.append(
            f"{index}. {item['title']}"
        )

        description = item.get(
            "description",
            ""
        )

        if description:

            lines.append(
                shorten(
                    description,
                    140
                )
            )

        lines.append("")

    return lines


# ============================================================
# 生成整篇早报
# ============================================================

def build_message(
    markets,
    news
):

    today = datetime.datetime.now()

    date_text = today.strftime(
        "%m月%d日"
    )

    weekday = [
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
        "星期日",
    ][today.weekday()]

    lines = []

    # ========================================================
    # 标题
    # ========================================================

    lines.append(
        "💰 今日经济早报"
    )

    lines.append(
        f"{date_text} · {weekday}"
    )

    lines.append("")

    # ========================================================
    # 市场数据
    # ========================================================

    lines.append(
        "📈 今夜市场"
    )

    lines.append("")

    market_order = [
        "gold",
        "oil",
        "sp500",
        "nasdaq",
        "usd",
        "us10y",
    ]

    for key in market_order:

        if key not in markets:

            continue

        item = markets[key]

        lines.append(
            f"{item['name']}  "
            f"{format_market(item)}"
        )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━"
    )

    lines.append("")

    # ========================================================
    # 市场一句话
    # ========================================================

    lines.append(
        "🧭 今天怎么看"
    )

    lines.append("")

    lines.append(
        market_comment(markets)
    )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━"
    )

    lines.append("")

    # ========================================================
    # 新闻排序
    # ========================================================

    news = deduplicate_news(news)

    news.sort(
        key=score_news,
        reverse=True
    )

    # ========================================================
    # 今日头条
    # ========================================================

    if news:

        top = news[0]

        lines.append(
            "🔥 今天最值得关注"
        )

        lines.append("")

        lines.append(
            top["title"]
        )

        description = top.get(
            "description",
            ""
        )

        if description:

            lines.append("")

            lines.append(
                shorten(
                    description,
                    220
                )
            )

        lines.append("")

        lines.append(
            "━━━━━━━━━━━━"
        )

        lines.append("")

    # ========================================================
    # 其他新闻
    # ========================================================

    global_news = [
        item
        for item in news
        if item["category"] == "全球经济"
    ]

    market_news = [
        item
        for item in news
        if item["category"] == "全球市场"
    ]

    lines.extend(
        build_news_section(
            global_news,
            "🌍 全球经济",
            3
        )
    )

    if global_news:

        lines.append(
            "━━━━━━━━━━━━"
        )

        lines.append("")

    lines.extend(
        build_news_section(
            market_news,
            "📊 全球市场",
            3
        )
    )

    if market_news:

        lines.append(
            "━━━━━━━━━━━━"
        )

        lines.append("")

    # ========================================================
    # 最值得关注的关键词
    # ========================================================

    keyword_candidates = [
        "美联储",
        "降息",
        "加息",
        "通胀",
        "就业",
        "GDP",
        "黄金",
        "原油",
        "美元",
        "美债",
        "中国",
        "关税",
    ]

    matched = []

    all_titles = " ".join(
        item["title"]
        for item in news
    ).lower()

    for keyword in keyword_candidates:

        if keyword.lower() in all_titles:

            matched.append(keyword)

    if matched:

        lines.append(
            "👀 今天重点盯住"
        )

        lines.append("")

        lines.append(
            " · ".join(
                matched[:8]
            )
        )

        lines.append("")

    # ========================================================
    # 结尾
    # ========================================================

    lines.append(
        "━━━━━━━━━━━━"
    )

    lines.append("")

    lines.append(
        "钱从哪里来，往哪里去，"
    )

    lines.append(
        "核心还是看利率、增长和流动性。"
    )

    lines.append("")

    lines.append(
        "来源：公开财经新闻与市场数据"
    )

    return "\n".join(lines)


# ============================================================
# Bark 推送
# ============================================================

def push_bark(
    title,
    body,
    url=None
):

    if not BARK_KEY:

        raise ValueError(
            "没有设置 BARK_KEY"
        )

    payload = {

        "device_key": BARK_KEY,

        "title": title,

        "body": body,

        "group": "经济早报",

        "sound": "minuet",

        "level": "active",

    }

    # 点击通知打开头条
    if url:

        payload["url"] = url

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(

        f"{BARK_SERVER}/push",

        data=data,

        method="POST",

        headers={
            "Content-Type":
                "application/json; charset=utf-8",

            "User-Agent":
                UA,
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.read().decode(
            "utf-8"
        )


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "正在获取市场数据..."
    )

    markets = get_markets()

    print(
        f"成功获取 {len(markets)} 个市场数据"
    )

    print(
        "正在获取财经新闻..."
    )

    news = get_news()

    print(
        f"成功获取 {len(news)} 条新闻"
    )

    # --------------------------------------------------------
    # 找到头条 URL
    # --------------------------------------------------------

    sorted_news = deduplicate_news(news)

    sorted_news.sort(
        key=score_news,
        reverse=True
    )

    top_url = ""

    if sorted_news:

        top_url = sorted_news[0].get(
            "url",
            ""
        )

    # --------------------------------------------------------
    # 生成正文
    # --------------------------------------------------------

    body = build_message(
        markets,
        news
    )

    today = datetime.datetime.now().strftime(
        "%m/%d"
    )

    title = f"💰 经济早报 · {today}"

    # --------------------------------------------------------
    # 打印预览
    # --------------------------------------------------------

    print()
    print("=" * 50)
    print(body)
    print("=" * 50)
    print()

    # --------------------------------------------------------
    # Bark
    # --------------------------------------------------------

    push_bark(
        title,
        body,
        top_url
    )

    print(
        "✅ 经济早报已推送到 iPhone"
    )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    main()