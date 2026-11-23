#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import urllib.parse
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
    USE_CFFI = True
except ImportError:
    USE_CFFI = False

BJT = pytz.timezone("Asia/Shanghai")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# ==================== 15 款监测相机配置（已移除所有排除词，仅保留宽松型号匹配） ====================
TARGETS = [
    {
        "name": "哈苏 500CX / 503CX",
        "query": "HASSELBLAD 503CX",
        "keywords": ["503cx", "500cx"],
    },
    {
        "name": "哈苏 500C/M",
        "query": "HASSELBLAD 500C/M",
        "keywords": ["500c/m", "500cm", "500 c/m"],
    },
    {
        "name": "哈苏 503CW",
        "query": "HASSELBLAD 503CW",
        "keywords": ["503cw"],
    },
    {
        "name": "徕卡 M6 复刻版",
        "query": "Leica M6 復刻",
        "keywords": ["m6"],
    },
    {
        "name": "徕卡 M6 Ti (钛版)",
        "query": "Leica M6 チタン",
        "keywords": ["m6"],
    },
    {
        "name": "康泰时 Contax 645",
        "query": "CONTAX 645",
        "keywords": ["645"],
    },
    {
        "name": "尼康 Nikon 35Ti",
        "query": "Nikon 35Ti",
        "keywords": ["35ti", "35 ti"],
    },
    {
        "name": "尼康 Nikon 28Ti",
        "query": "Nikon 28Ti",
        "keywords": ["28ti", "28 ti"],
    },
    {
        "name": "理光 Ricoh GR1s",
        "query": "RICOH GR1s",
        "keywords": ["gr1s", "gr 1s"],
    },
    {
        "name": "奥林巴斯 Olympus μ1",
        "query": "OLYMPUS μ",
        "keywords": ["μ", "mju", "ミュー"],
    },
    {
        "name": "康泰时 Contax T3",
        "query": "CONTAX T3",
        "keywords": ["t3"],
    },
    {
        "name": "康泰时 Contax G2",
        "query": "CONTAX G2",
        "keywords": ["g2"],
    },
    {
        "name": "美能达 Minolta TC-1",
        "query": "MINOLTA TC-1",
        "keywords": ["tc-1", "tc1"],
    },
    {
        "name": "柯尼卡 巧思 Konica HEXAR RF",
        "query": "Konica HEXAR RF",
        "keywords": ["hexar", "ヘキサー"],
    },
    {
        "name": "柯尼卡 巧思 Konica HEXAR AF",
        "query": "Konica HEXAR",
        "keywords": ["hexar", "ヘキサー"],
    },
]


def http_get(url: str, params: dict = None):
    if USE_CFFI:
        return cffi_requests.get(
            url, params=params, headers=HEADERS, impersonate="chrome120", timeout=20
        )
    return requests.get(url, params=params, headers=HEADERS, timeout=20)


def match_model(title: str, target: dict) -> bool:
    """宽松匹配：只要标题含任意一个目标型号词即放行，不做任何书籍/说明书/配件过滤"""
    t_lower = title.lower()
    if not target.get("keywords"):
        return True
    return any(k in t_lower for k in target["keywords"])


def parse_remaining_time(time_str: str, end_timestamp_ms: str = None):
    is_within_1h = False
    end_display = time_str.strip() if time_str else "进行中"

    if end_timestamp_ms and str(end_timestamp_ms).isdigit():
        end_ts = int(end_timestamp_ms) / 1000.0
        diff_sec = end_ts - time.time()
        if 0 < diff_sec <= 3600:
            is_within_1h = True
        end_dt_bjt = datetime.fromtimestamp(end_ts, BJT).strftime("%m-%d %H:%M")
        rem_min = max(0, int(diff_sec // 60))
        if 0 < diff_sec <= 3600:
            end_display = f"{end_dt_bjt} (仅剩 {rem_min} 分钟!)"
        else:
            end_display = f"{end_dt_bjt} ({end_display})"
        return end_display, is_within_1h

    if re.search(r"(?:残り\s*)?(?:\d+分|\d+秒)$", end_display) and "時間" not in end_display and "日" not in end_display:
        is_within_1h = True
    return end_display, is_within_1h


def parse_yahoo_html(html_text: str, target: dict):
    """解析雅虎拍卖搜索结果页（兼容经典 DOM 与新版链接反查）"""
    soup = BeautifulSoup(html_text, "html.parser")
    raw_items = []

    # 1. 经典 li.Product 节点
    for prod in soup.select("li.Product"):
        title_el = prod.select_one("a.Product__titleLink")
        price_el = prod.select_one("span.Product__priceValue")
        time_el = prod.select_one("span.Product__time")
        bonus_el = prod.select_one(".Product__bonus")
        if not title_el or not price_el:
            continue
        raw_items.append({
            "title": title_el.get_text(strip=True),
            "link": title_el.get("href", "").split("?")[0],
            "price": price_el.get_text(strip=True),
            "raw_time": time_el.get_text(strip=True) if time_el else "进行中",
            "end_ts_ms": bonus_el.get("data-auction-endtime") if bonus_el else None,
        })

    # 2. 若经典节点为空，直接检索页面所有 /jp/auction/ 链接
    if not raw_items:
        seen_ids = set()
        for a_tag in soup.find_all("a", href=re.compile(r"/jp/auction/[a-zA-Z0-9]+")):
            href = a_tag.get("href", "").split("?")[0]
            m_id = re.search(r"/jp/auction/([a-zA-Z0-9]+)", href)
            if not m_id:
                continue
            aid = m_id.group(1)
            if aid in seen_ids:
                continue

            title_text = a_tag.get_text(strip=True) or a_tag.get("title", "").strip()
            if len(title_text) < 3:
                continue
            seen_ids.add(aid)

            container = a_tag.find_parent("li") or a_tag.find_parent("div")
            block_text = container.get_text(" ", strip=True) if container else title_text

            price_match = re.search(r"([\d,]+\s*円)", block_text)
            price_str = price_match.group(1) if price_match else "详见链接"

            time_match = re.search(r"(残り\s*\d+\s*(?:日|時間|分|秒)|\d+\s*(?:日|時間|分|秒)|本日終了)", block_text)
            time_str = time_match.group(1) if time_match else "进行中"

            full_link = href if href.startswith("http") else f"https://auctions.yahoo.co.jp{href}"
            raw_items.append({
                "title": title_text,
                "link": full_link,
                "price": price_str,
                "raw_time": time_str,
                "end_ts_ms": None,
            })

    results = []
    for item in raw_items:
        if not match_model(item["title"], target):
            continue
        end_info, within_1h = parse_remaining_time(item["raw_time"], item["end_ts_ms"])
        results.append({
            "model": target["name"],
            "title": item["title"],
            "price": item["price"],
            "end_info": end_info,
            "within_1h": within_1h,
            "link": item["link"],
        })

    return len(raw_items), results


def fetch_zenmarket_fallback(target: dict):
    """
    第二数据源兜底（ZenMarket 雅虎拍卖实时镜像）：
    直接提取 itemCode 还原为雅虎拍卖原链接，不受海外机房 IP 屏蔽影响
    """
    encoded_q = urllib.parse.quote(target["query"])
    url = f"https://zenmarket.jp/en/yahoo.aspx?q={encoded_q}"
    results = []
    raw_count = 0
    try:
        resp = http_get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        seen_ids = set()

        for a_tag in soup.find_all("a", href=re.compile(r"itemCode=[a-zA-Z0-9]+")):
            href = a_tag.get("href", "")
            m_id = re.search(r"itemCode=([a-zA-Z0-9]+)", href)
            if not m_id:
                continue
            aid = m_id.group(1)
            if aid in seen_ids:
                continue

            title = a_tag.get_text(strip=True) or a_tag.get("title", "").strip()
            if len(title) < 3:
                continue
            seen_ids.add(aid)
            raw_count += 1

            if not match_model(title, target):
                continue

            container = a_tag.find_parent("div", class_=re.compile(r"product|item|card", re.I)) or a_tag.find_parent("div")
            block_text = container.get_text(" ", strip=True) if container else ""
            price_match = re.search(r"(?:¥|JPY\s*)([\d,]+)|([\d,]+)\s*(?:円|JPY)", block_text, re.I)
            if price_match:
                num = price_match.group(1) or price_match.group(2)
                price_str = f"{num}円"
            else:
                price_str = "详见链接"

            results.append({
                "model": target["name"],
                "title": title,
                "price": price_str,
                "end_info": "日拍实时在拍",
                "within_1h": False,
                "link": f"https://auctions.yahoo.co.jp/jp/auction/{aid}",
            })
    except Exception as e:
        print(f"  [ZenMarket 兜底异常] {target['name']}: {e}")

    return raw_count, results


def fetch_yahoo_auctions(target: dict, mode: str = "auction"):
    url = "https://auctions.yahoo.co.jp/search/search"
    params = {
        "p": target["query"],
        "tab_ex": "commerce",
        "ei": "UTF-8",
        "b": "1",
        "n": "50",
    }
    if mode == "auction":
        params["fixed"] = "2"  # 竞拍 (オークション)
        params["s1"] = "end"
        params["o1"] = "a"
    else:
        params["fixed"] = "1"  # 定额一口价 (定額)
        params["s1"] = "new"
        params["o1"] = "d"

    try:
        resp = http_get(url, params=params)
        raw_count, results = parse_yahoo_html(resp.text, target)
        print(f"[{target['name']} - {mode}] 雅虎直连 HTTP {resp.status_code} | 原始 {raw_count} 条 -> 匹配 {len(results)} 条")

        # 若雅虎主站在海外机房下返回 0 条，自动切换 ZenMarket 镜像抓取
        if raw_count == 0 and mode == "auction":
            z_raw, z_res = fetch_zenmarket_fallback(target)
            print(f"  ↳ [ZenMarket 镜像兜底] {target['name']}: 原始 {z_raw} 条 -> 匹配 {len(z_res)} 条")
            return z_res

        return results
    except Exception as e:
        print(f"[ERROR] 抓取 {target['name']} ({mode}) 异常: {e}")
        if mode == "auction":
            _, z_res = fetch_zenmarket_fallback(target)
            return z_res
        return []


def build_markdown_report(now_str: str, urgent_auctions: list, all_auctions: list, all_fixed: list) -> str:
    lines = [
        f"### 📡 雅虎拍卖 15 款相机监测 ({now_str} 北京时间)",
        "已放宽检索词（无书刊/配件拦截，全量展示匹配商品）\n",
    ]

    lines.append(f"#### 🚨 一、 距结束不足 1 小时的竞拍 ({len(urgent_auctions)}件)")
    if not urgent_auctions:
        lines.append("当前暂无 1 小时内截标的目标机型。\n")
    else:
        for i, it in enumerate(urgent_auctions, 1):
            lines.append(
                f"{i}. 🔥 **[{it['model']}]** 价格: `{it['price']}` | 结束: **{it['end_info']}**\n"
                f"   - 简介: {it['title']}\n"
                f"   - [👉 点击打开拍卖链接]({it['link']})\n"
            )

    lines.append(f"\n#### 🔨 二、 在拍商品列表 (共 {len(all_auctions)} 件，展示前 30 件)")
    if not all_auctions:
        lines.append("当前暂无符合条件的在拍商品。\n")
    else:
        for it in all_auctions[:30]:
            tag = "🔥" if it["within_1h"] else "•"
            lines.append(
                f"{tag} **[{it['model']}]** `{it['price']}` | 结束: {it['end_info']}\n"
                f"  {it['title']} — [拍卖链接]({it['link']})"
            )

    lines.append(f"\n#### 🛍️ 三、 定额在售商品 (共 {len(all_fixed)} 件，展示前 30 件)")
    if not all_fixed:
        lines.append("当前暂无符合条件的定额在售商品。\n")
    else:
        for it in all_fixed[:30]:
            lines.append(
                f"• **[{it['model']}]** 在售价: `{it['price']}`\n"
                f"  {it['title']} — [在售链接]({it['link']})"
            )

    return "\n".join(lines)


def push_to_wechat(title: str, md_content: str):
    raw_tokens = os.getenv("PUSHPLUS_TOKEN", "")
    token_2 = os.getenv("PUSHPLUS_TOKEN_2", "")
    combined = f"{raw_tokens},{token_2}"

    tokens = [
        t.strip().strip('"').strip("'")
        for t in re.split(r"[,;\s\n]+", combined)
        if t.strip().strip('"').strip("'")
    ]

    if not tokens:
        print("💡 未检测到 PUSHPLUS_TOKEN 环境变量，跳过微信推送。")
        return

    for idx, tok in enumerate(tokens, 1):
        masked = f"{tok[:4]}***{tok[-4:]}" if len(tok) > 8 else tok
        print(f"正在向第 {idx} 个微信发送推送 (Token: {masked}, 长度: {len(tok)}位)...")
        try:
            r = requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": tok,
                    "title": title,
                    "content": md_content,
                    "template": "markdown",
                },
                timeout=15,
            )
            print(f"✅ [第 {idx} 人微信 PushPlus 推送结果]: {r.text}")
        except Exception as e:
            print(f"❌ [第 {idx} 人微信 PushPlus 推送失败]: {e}")


def main():
    print(f"🔧 当前 HTTP 引擎: {'curl_cffi (Chrome120 指纹模拟)' if USE_CFFI else 'requests 标准库'}")
    now_str = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    urgent_auctions = []
    all_auctions = []
    all_fixed = []

    seen_auction_links = set()
    seen_fixed_links = set()

    for target in TARGETS:
        auctions = fetch_yahoo_auctions(target, mode="auction")
        for item in auctions:
            if item["link"] not in seen_auction_links:
                seen_auction_links.add(item["link"])
                all_auctions.append(item)
                if item["within_1h"]:
                    urgent_auctions.append(item)
        time.sleep(0.5)

        fixed_items = fetch_yahoo_auctions(target, mode="fixed")
        for item in fixed_items:
            if item["link"] not in seen_fixed_links:
                seen_fixed_links.add(item["link"])
                all_fixed.append(item)
        time.sleep(0.5)

    report_md = build_markdown_report(now_str, urgent_auctions, all_auctions, all_fixed)
    print("\n" + report_md)

    if urgent_auctions:
        push_title = f"🚨【紧急! {len(urgent_auctions)}件1小时内截标】15款日拍相机 ({now_str})"
    else:
        push_title = f"📷 日拍15款相机整点监测 ({now_str} | 在拍{len(all_auctions)}件)"

    push_to_wechat(push_title, report_md)


if __name__ == "__main__":
    main()
