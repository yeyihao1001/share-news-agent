import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


TZ = timezone(timedelta(hours=8))
OUT = Path("daily-report.json")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_URL = f"{OPENAI_BASE_URL}/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

EASTMONEY_COLUMNS = [
    {"name": "东方财富财经快讯", "column": "351"},
    {"name": "东方财富A股快讯", "column": "345"},
    {"name": "东方财富市场快讯", "column": "344"},
]

RSS_SOURCES = [
    {"name": "雪球今日话题", "url": "https://xueqiu.com/hots/topic/rss"},
]

SECTOR_RULES = [
    {
        "name": "AI算力 / 光模块",
        "keywords": ["人工智能", "AI", "算力", "数据中心", "光模块", "服务器", "英伟达", "大模型", "Kimi", "开源模型", "光通信"],
        "trend": "偏利好",
        "stocks": [
            {"name": "中际旭创", "code": "300308", "quality": "行业地位强", "reason": "高速光模块代表公司，和海外 AI 资本开支相关度较高。", "risk": "短线涨幅大时容易受情绪波动影响。"},
            {"name": "新易盛", "code": "300502", "quality": "弹性较强", "reason": "光模块弹性标的，受 AI 网络建设预期影响明显。", "risk": "估值和订单兑现节奏需要跟踪。"},
            {"name": "工业富联", "code": "601138", "quality": "产业链核心", "reason": "AI 服务器产业链代表公司，和算力基础设施相关。", "risk": "体量较大，短线弹性通常弱于高弹性标的。"},
        ],
    },
    {
        "name": "半导体 / 国产替代",
        "keywords": ["半导体", "芯片", "国产替代", "光刻", "设备", "晶圆", "先进封装", "存储", "SK海力士", "三星电子"],
        "trend": "事件驱动",
        "stocks": [
            {"name": "北方华创", "code": "002371", "quality": "设备龙头", "reason": "半导体设备龙头，国产替代主线相关度高。", "risk": "估值较高，短线受政策和订单预期影响大。"},
            {"name": "中微公司", "code": "688012", "quality": "设备代表", "reason": "半导体设备代表公司，受晶圆厂资本开支影响。", "risk": "科创板波动较大，需要关注成交量。"},
            {"name": "长电科技", "code": "600584", "quality": "封装代表", "reason": "先进封装相关标的，受 AI 芯片封装需求影响。", "risk": "行业周期和利润弹性需要验证。"},
        ],
    },
    {
        "name": "新能源车 / 电池",
        "keywords": ["新能源", "电池", "锂电", "电池材料", "价格竞争", "储能", "碳酸锂", "充电桩", "电力设备"],
        "trend": "分歧加大",
        "stocks": [
            {"name": "宁德时代", "code": "300750", "quality": "龙头", "reason": "动力电池龙头，产业链景气变化会直接影响市场预期。", "risk": "价格战和材料价格波动会压制短线情绪。"},
            {"name": "比亚迪", "code": "002594", "quality": "整车龙头", "reason": "整车与电池一体化代表公司，新能源车销量变化相关度高。", "risk": "价格竞争加剧会影响利润预期。"},
            {"name": "天赐材料", "code": "002709", "quality": "材料代表", "reason": "电解液材料代表公司，受材料价格和需求变化影响。", "risk": "周期属性较强，短线需关注报价变化。"},
        ],
    },
    {
        "name": "白酒 / 消费",
        "keywords": ["白酒", "消费", "渠道", "中秋", "备货", "高端酒", "茅台", "五粮液", "零售"],
        "trend": "偏谨慎",
        "stocks": [
            {"name": "贵州茅台", "code": "600519", "quality": "高端核心", "reason": "高端白酒核心标的，渠道反馈会影响消费板块预期。", "risk": "短线弹性较弱，更适合观察消费情绪变化。"},
            {"name": "五粮液", "code": "000858", "quality": "高端代表", "reason": "高端白酒代表公司，对动销和批价变化敏感。", "risk": "渠道信心弱时估值修复可能放缓。"},
            {"name": "泸州老窖", "code": "000568", "quality": "弹性代表", "reason": "白酒弹性代表之一，受行业景气和渠道反馈影响。", "risk": "短线跟随板块情绪波动。"},
        ],
    },
    {
        "name": "医药 / 创新药",
        "keywords": ["医药", "创新药", "药企", "临床", "集采", "医疗", "CXO", "疫苗"],
        "trend": "事件驱动",
        "stocks": [
            {"name": "恒瑞医药", "code": "600276", "quality": "创新药龙头", "reason": "创新药代表公司，受临床进展和政策预期影响。", "risk": "研发兑现和估值修复节奏需要观察。"},
            {"name": "药明康德", "code": "603259", "quality": "CXO代表", "reason": "医药外包代表公司，受全球创新药景气影响。", "risk": "海外政策和订单预期会影响短线情绪。"},
            {"name": "迈瑞医疗", "code": "300760", "quality": "器械龙头", "reason": "医疗器械核心公司，受医疗设备需求影响。", "risk": "板块风险偏好不足时弹性较弱。"},
        ],
    },
    {
        "name": "金融 / 券商",
        "keywords": ["券商", "证券", "保险", "银行", "降息", "美联储", "加息", "流动性", "汇率"],
        "trend": "宏观驱动",
        "stocks": [
            {"name": "东方财富", "code": "300059", "quality": "互联网券商", "reason": "市场成交活跃度和风险偏好变化会影响券商弹性。", "risk": "高度依赖市场成交量和指数情绪。"},
            {"name": "中信证券", "code": "600030", "quality": "券商龙头", "reason": "券商龙头，适合观察金融板块整体风险偏好。", "risk": "短线弹性通常低于小市值券商。"},
            {"name": "招商银行", "code": "600036", "quality": "银行核心", "reason": "利率、宏观预期和信用环境会影响银行估值。", "risk": "短线更多受宏观和指数风格影响。"},
        ],
    },
]


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="ignore")


def fetch_eastmoney(column: dict) -> list[dict]:
    params = {
        "client": "web",
        "biz": "web_news_col",
        "column": column["column"],
        "page_index": "1",
        "page_size": "12",
        "req_trace": uuid.uuid4().hex,
    }
    url = f"https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?{urlencode(params)}"
    try:
        data = json.loads(fetch_text(url))
    except Exception as exc:
        return [{
            "title": f"{column['name']} 抓取失败",
            "summary": str(exc),
            "url": url,
            "source": column["name"],
            "published": "",
        }]

    items = []
    for item in (data.get("data") or {}).get("list", [])[:12]:
        title = clean(item.get("title", ""))
        if not title:
            continue
        items.append({
            "title": title,
            "summary": clean(item.get("summary", "")),
            "url": item.get("url") or item.get("uniqueUrl") or "",
            "published": item.get("showTime", ""),
            "source": item.get("mediaName") or column["name"],
        })
    return items


def fetch_rss(source: dict) -> list[dict]:
    try:
        raw = fetch_text(source["url"])
    except (HTTPError, URLError, TimeoutError) as exc:
        return [{
            "title": f"{source['name']} 抓取失败",
            "summary": str(exc),
            "url": source["url"],
            "source": source["name"],
            "published": "",
        }]

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    items = []
    for item in root.findall(".//item")[:12]:
        title = clean(item.findtext("title"))
        if not title:
            continue
        items.append({
            "title": title,
            "summary": clean(item.findtext("description")),
            "url": clean(item.findtext("link")),
            "published": clean(item.findtext("pubDate")),
            "source": source["name"],
        })
    return items


def parse_news_time(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None


def enrich_freshness(items: list[dict], now: datetime) -> list[dict]:
    for item in items:
        dt = parse_news_time(item.get("published", ""))
        item["published_at"] = dt.isoformat() if dt else ""
        item["published_label"] = dt.strftime("%Y-%m-%d %H:%M") if dt else item.get("published", "")
        item["is_today"] = bool(dt and dt.date() == now.date())
    return items


def collect_news(now: datetime) -> tuple[list[dict], list[dict]]:
    seen = set()
    results = []
    source_status = []

    for source in EASTMONEY_COLUMNS:
        items = fetch_eastmoney(source)
        source_status.append({"name": source["name"], "items": len(items), "type": "realtime"})
        for item in items:
            key = item["title"]
            if key not in seen:
                seen.add(key)
                results.append(item)
        time.sleep(0.25)

    for source in RSS_SOURCES:
        items = fetch_rss(source)
        source_status.append({"name": source["name"], "items": len(items), "type": "rss"})
        for item in items:
            key = item["title"]
            if key not in seen:
                seen.add(key)
                results.append(item)
        time.sleep(0.25)

    enrich_freshness(results, now)
    results.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return results[:30], source_status


def impact_direction(trend: str) -> str:
    if trend == "偏利好":
        return "偏正向"
    if trend == "偏谨慎":
        return "偏负向 / 需观察"
    if trend == "分歧加大":
        return "多空分歧"
    return trend


def build_news_analysis(news_items: list[dict]) -> list[dict]:
    analyses = []
    for item in news_items:
        text = f"{item['title']} {item.get('summary', '')}"
        matched = []
        for sector in SECTOR_RULES:
            hits = [kw for kw in sector["keywords"] if kw in text]
            if not hits:
                continue
            matched.append({
                "sector": sector["name"],
                "direction": impact_direction(sector["trend"]),
                "hits": hits[:6],
                "logic": f"新闻命中{sector['name']}相关关键词，适合作为短线板块观察线索，先看板块强度和龙头反馈。",
                "watch_stocks": sector["stocks"][:3],
                "risk": "新闻热度不等于股价持续上涨，需要防止高开低走、题材兑现和市场情绪转弱。",
            })

        if not matched:
            matched.append({
                "sector": "未命中内置板块",
                "direction": "暂不判断",
                "hits": [],
                "logic": "这条新闻暂时没有命中当前行业词库，先保留为信息观察，后续可扩展关键词和股票池。",
                "watch_stocks": [],
                "risk": "不要为了每条新闻强行关联股票，无法建立清晰影响链条时应保持空白。",
            })

        analyses.append({
            "title": item["title"],
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "published": item.get("published", ""),
            "published_label": item.get("published_label", ""),
            "is_today": item.get("is_today", False),
            "summary": item.get("summary", "")[:220],
            "impacts": matched[:3],
        })
    return analyses


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def call_openai(news_items: list[dict]) -> dict | None:
    token = os.environ.get("OPENAI_API_KEY", "").strip()
    if not token:
        return None

    compact_news = [
        {
            "title": item.get("title", "")[:120],
            "summary": item.get("summary", "")[:260],
            "source": item.get("source", ""),
            "published": item.get("published_label") or item.get("published", ""),
            "is_today": item.get("is_today", False),
            "url": item.get("url", ""),
        }
        for item in news_items[:12]
    ]

    prompt = {
        "role": "A股短线新闻情报分析助手",
        "rules": [
            "只做信息整理、影响链路分析和风险提示，不输出买入、卖出、必涨、收益承诺。",
            "优先分析 is_today=true 的新闻；如果新闻不是当天，要提醒数据源可能滞后。",
            "每条新闻都要给出独立分析，不能只做总体总结。",
            "如果新闻与股票影响链路不清晰，要写暂不判断，不要强行关联。",
            "语言要像专业投研/产品工具输出，简洁、克制、可展示在网页里。",
        ],
        "output_json_shape": {
            "ai_summary": "今日整体短线情绪概括，80字以内",
            "ai_market_view": "今日更值得关注的主线和不确定性，120字以内",
            "ai_focus": [
                {
                    "theme": "主题名称",
                    "reason": "为什么值得关注",
                    "sectors": ["相关板块"],
                    "attention": "盘中观察点",
                    "risk": "风险点",
                }
            ],
            "ai_news_analysis": [
                {
                    "title": "必须对应输入新闻标题",
                    "impact": "这条新闻可能影响什么方向",
                    "direction": "偏正向/偏负向/多空分歧/暂不判断",
                    "sectors": ["相关板块"],
                    "watch_logic": "观察逻辑",
                    "risk": "风险提醒",
                }
            ],
        },
        "news": compact_news,
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个谨慎的A股短线新闻情报分析助手，只输出JSON，不输出投资建议。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    req = Request(
        OPENAI_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ai_enabled": False, "ai_error": f"AI分析调用失败：{exc}"}

    try:
        text = data["choices"][0]["message"]["content"]
        result = extract_json(text)
        result["ai_enabled"] = True
        result["ai_model"] = OPENAI_MODEL
        result["ai_base_url"] = OPENAI_BASE_URL
        return result
    except Exception as exc:
        return {"ai_enabled": False, "ai_error": f"AI分析结果解析失败：{exc}"}


def analyze(news_items: list[dict]) -> dict:
    full_text = "\n".join(f"{n['title']} {n.get('summary', '')}" for n in news_items)
    sectors = []
    candidates = []

    for sector in SECTOR_RULES:
        hits = [kw for kw in sector["keywords"] if kw in full_text]
        related_news = [
            n for n in news_items
            if any(kw in f"{n['title']} {n.get('summary', '')}" for kw in sector["keywords"])
        ][:5]
        if not hits and not related_news:
            continue

        heat = min(100, 62 + len(hits) * 5 + len(related_news) * 3)
        sectors.append({
            "name": sector["name"],
            "trend": sector["trend"],
            "hits": hits[:8],
            "heat": heat,
            "related_news": related_news,
            "short_view": "先看板块是否放量走强，再看龙头是否高开低走。新闻只作为筛选线索，不直接等同于交易信号。",
        })

        for idx, stock in enumerate(sector["stocks"]):
            item = dict(stock)
            item.update({"sector": sector["name"], "trend": sector["trend"], "score": max(68, heat - idx * 5)})
            candidates.append(item)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    risk_level = "中高" if any(s["trend"] in ("偏谨慎", "分歧加大") for s in sectors) else ("中等" if sectors else "待观察")

    result = {
        "sectors": sectors,
        "candidates": candidates[:12],
        "news_analysis": build_news_analysis(news_items),
        "risk_level": risk_level,
    }
    ai_result = call_openai(news_items)
    if ai_result:
        result.update(ai_result)
    else:
        result.update({"ai_enabled": False, "ai_error": "未配置 OPENAI_API_KEY，当前使用规则分析。"})
    return result


def build_freshness(news_items: list[dict], now: datetime, source_status: list[dict]) -> dict:
    today_count = sum(1 for item in news_items if item.get("is_today"))
    latest = next((item for item in news_items if item.get("published_label")), None)
    return {
        "today_count": today_count,
        "total_count": len(news_items),
        "latest_news_time": latest.get("published_label", "") if latest else "",
        "latest_news_source": latest.get("source", "") if latest else "",
        "is_fresh": today_count > 0,
        "warning": "" if today_count > 0 else "当前新闻源未抓到今日新闻，数据可能滞后。",
        "sources": source_status,
    }


def main() -> None:
    now = datetime.now(TZ)
    news_items, source_status = collect_news(now)
    analysis = analyze(news_items)
    payload = {
        "version": "V3.1",
        "generated_at": now.isoformat(),
        "generated_label": now.strftime("%Y-%m-%d %H:%M"),
        "market": "A股",
        "style": "短线新闻驱动",
        "source_note": "东方财富快讯 + 雪球RSS + AI/规则分析；结果用于信息整理，不构成投资建议。",
        "freshness": build_freshness(news_items, now, source_status),
        "news": news_items,
        **analysis,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"daily report generated: {OUT} ({len(news_items)} news, {payload['freshness']['today_count']} today)")


if __name__ == "__main__":
    main()
