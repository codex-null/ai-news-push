# 把 AI 资讯自动推送到手机

三步自动化：拉数据 → 整理 → 推到你手机。数据来自 [aihot.virxact.com](https://aihot.virxact.com)（公开匿名接口，无需 token）。

## 文件清单
- `ai_news_push.py` —— 主脚本，拉 AI HOT 日报并推送
- `.github/workflows/ai-news.yml` —— GitHub Actions 定时任务（免费、零服务器、每天北京时间 08:00 自动跑）
- `ai-hot-briefing-2026-09-11.html` —— 今日已生成的精选简报样例

## 选一个手机推送通道
| 通道 | 适合 | 需要 |
|------|------|------|
| **Bark** | iPhone 用户，免费、秒到、无广告 | App Store 装 Bark，复制里的 key |
| **Server 酱 / PushPlus** | 想推到微信 | 微信扫码拿 token |
| **Email** | 任意手机，收邮件通知 | 一个邮箱的 SMTP 授权码 |

## 方式一：本地 / 任意云服务器跑（cron）
```bash
pip install requests
export PUSH_CHANNEL=bark
export BARK_KEY=你的key
python3 ai_news_push.py

# 想每天 08:00 自动跑，加到 crontab：
# 0 8 * * * cd /你的目录 && PUSH_CHANNEL=bark BARK_KEY=xxx /usr/bin/python3 ai_news_push.py
```

## 方式二：GitHub Actions 零成本托管（推荐，不用开服务器）
1. 把这个目录推到 GitHub 仓库
2. 仓库 Settings → Secrets → 加 `PUSH_CHANNEL`、`BARK_KEY`（或 `SERVERCHAN_KEY` / 邮箱相关）
3. 脚本每天 UTC 0:00（=北京时间 08:00）自动运行，新闻直接弹到你手机

## 想推「精选」而不是「日报」？
脚本默认拉每日成品日报。如果想推最近 24 小时滚动精选，把 `get_daily()` 换成拉
`items?mode=selected&since=<24小时前>` 即可（接口文档见 aihot 站点 /openapi.yaml）。
