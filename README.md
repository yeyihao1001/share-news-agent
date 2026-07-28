# A股短线情报 Agent

这是一个部署到 GitHub Pages 的网页工具原型。它每天通过 GitHub Actions 自动抓取公开财经新闻，生成 `daily-report.json`，网页端读取 JSON 后展示新闻时效性、AI 总结、新闻影响板块、候选观察池和风险提示。

## 文件

- `index.html`：网页主文件，手机和电脑都可以打开。
- `news_agent.py`：自动抓取新闻并生成 `daily-report.json`。
- `.github/workflows/daily-report.yml`：每天定时运行脚本并提交日报。
- `daily-report.json`：自动生成的网页数据文件。

## V3.1 数据源升级

V3.1 优先使用东方财富快讯接口，补充雪球 RSS，并在日报里新增 `freshness` 字段：

- `today_count`：抓到的当天新闻数量
- `latest_news_time`：最新新闻发布时间
- `is_fresh`：是否抓到当天新闻
- `sources`：各数据源抓取条数

这样可以区分“日报今天运行了”和“新闻源是否真的更新了”。

## AI 接入

V3 支持在 GitHub Actions 中调用 OpenAI API。需要在仓库 `Settings -> Secrets and variables -> Actions` 中新增：

- Secret：`OPENAI_API_KEY`
- Variable：`OPENAI_BASE_URL`，使用 Terln 时填写 `https://api.terln.com/v1`
- Variable：`OPENAI_MODEL`，使用 Terln GPT 5.4 Mini 时填写 `gpt-5.4-mini`

如果没有配置 API Key，项目会自动退回规则分析模式，网页仍可正常展示。

## 产品边界

当前版本用于展示“新闻驱动的短线信息整理流程”，不构成投资建议，不输出买入、卖出、必涨等交易指令。
