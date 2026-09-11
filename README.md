# AI News Push · 全球经济脉搏

这是一个面向手机阅读的经济新闻早报脚本。它会抓取公开 RSS 新闻和 Yahoo Finance 市场数据，生成深色科技风的响应式 HTML 仪表盘，并可通过 Bark 推送到 iPhone。

## 功能

- BBC Business、CNBC Markets、MarketWatch 经济新闻
- 黄金、原油、标普 500、纳斯达克、美元指数、美债 10Y
- 市场涨跌幅与内联 SVG 迷你走势图
- 新闻重要程度排序、主题关键词和情绪标签
- 响应式 HTML：电脑、手机均可阅读
- GitHub Actions 每天北京时间 08:00 自动运行
- Python 标准库实现，不需要安装第三方 Python 包

## 本地运行

```bash
# 使用示例数据预览页面，不访问网络，也不会推送
python ai_news_push.py --demo

# 抓取真实数据并生成 HTML，但不推送
python ai_news_push.py --no-push

# 配置 Bark 后抓取并推送
BARK_KEY=你的BarkKey python ai_news_push.py
```

报告默认输出到 `reports/`：

- `reports/economic_news_YYYY-MM-DD.html`：当天报告
- `reports/latest.html`：最新报告

Windows PowerShell：

```powershell
$env:BARK_KEY="你的BarkKey"
python .\ai_news_push.py
```

## GitHub Actions 配置

1. 在仓库 Settings → Secrets and variables → Actions 中添加 `BARK_KEY`。
2. 进入 Actions，手动运行 `AI 资讯每日推送` 可立即测试。
3. 工作流默认每天 UTC 00:00 运行，即北京时间 08:00。
4. 每次运行会上传 `economic-news-report` artifact，可在工作流详情页下载 HTML 报告。

如果你已经把报告部署到了 GitHub Pages 或其他公开地址，可以增加 Repository variable：

```text
REPORT_URL=https://你的地址/latest.html
```

Bark 通知会优先打开 `REPORT_URL`；没有设置时打开当天排名第一的新闻原文。

## 注意

- RSS 和市场接口可能临时限流或不可用，脚本会跳过失败的数据源并继续生成报告。
- 新闻情绪标签由关键词规则生成，仅用于快速扫读，不是投资建议。
- 市场价格可能存在延迟，不能替代交易终端或专业行情服务。
