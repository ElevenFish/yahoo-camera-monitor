#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import time
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

BJT = pytz.timezone("Asia/Shanghai")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,zh-CN;q=0.9,en;q=0.8",
    "Referer": "https://auctions.yahoo.co.jp/",
}

# ==================== 1. 升级版双语监测目标（扩大召回率） ====================
TARGETS = [
    {
        "name": "哈苏 500CX / 503CX",
        "query": "(HASSELBLAD OR ハッセルブラッド) (503CX OR 500CX)",
        "must_include_any": ["503cx", "500cx"],
        "must_include_all": [],
    },
    {
        "name": "哈苏 500C/M",
        "query": "(HASSELBLAD OR ハッセルブラッド) (500C/M OR 500CM)",
        "must_include_any": ["500c/m", "500cm"],
        "must_include_all": [],
    },
    {
        "name": "哈苏 503CW",
        "query": "(HASSELBLAD OR ハッセルブラッド) 503CW",
        "must_include_any": ["503cw"],
        "must_include_all": [],
    },
    {
        "name": "徕卡 M6 复刻版 (10557)",
        "query": "(Leica OR ライカ) M6 (復刻 OR 10557 OR 2022)",
        "must_include_any": ["復刻", "10557", "2022"],
        "must_include_all": ["m6"],
    },
    {
        "name": "徕卡 M6 Ti (钛版)",
        "query": "(Leica OR ライカ) M6 (チタン OR TITAN)",
        "must_include_any": ["チタン", "titan"],
        "must_include_all": ["m6"],
    },
    {
        "name": "康泰时 Contax 645 全套(不含镜头)",
        "query": "(CONTAX OR コンタックス) 645 (ボディ OR MFB-1 OR MF-1 OR KIT OR セット)",
        "must_include_any": ["ボディ", "body", "mf-1", "mfb-1", "kit", "セット"],
        "must_include_all": ["645"],
    },
]

# 精准排除词（不再误杀 "35mm" 胶片格式描述）
EXCLUDE_KEYWORDS = [
    "レンズセット", "レンズ付", "レンズ付き", "レンズつき", "+レンズ", "＋レンズ",
    "planar", "distagon", "sonnar", "biogon", "summicron", "summilux", "elmarit", "summaron",
    "f2.8", "f/2.8", "2.8/80", "2/50", "2/35", "1.4/50",
    "キャップのみ", "空箱", "説明書のみ", "ストラップのみ", "ジャンク品",
    "ファインダーのみ", "マガジンのみ", "後背のみ", "グリップのみ", "スクリーンのみ"
]

# 正则匹配类似 "80mm f2.8" / "50mm F2" 的镜头规格
LENS_SPEC_REGEX = re.compile(r"\b(35|45|50|55|80|90|110|120|140|150|210|250)\s*mm\s*f/?\d", re.I)


def is_valid_item(title: str, target: dict) -> bool:
    t_lower = title.lower()
    if target["must_include_any"] and not any(k in t_lower for k in target["must_include_any"]):
        return False
    for k in target["must_include_all"]:
        if k not in t_lower:
            return False
    for bad_word in EXCLUDE_KEYWORDS:
        if bad_word in t_lower:
            return False
    if LENS_SPEC_REGEX.search(title):
        return False
    return True


def parse_remaining_time(time_str: str, end_timestamp_ms: str = None):
    is_within_1h = False
    end_display = (time_str or "未知").strip()

    if end_timestamp_ms and str(end_timestamp_ms).isdigit():
        end_ts = int(end_timestamp_ms) / 1000.0
        diff_sec = end_ts - time.time()
        if 0 < diff_sec <= 3600:
            is_within_1h = True
        end_dt_bjt = datetime.fromtimestamp(end_ts, BJT).strftime("%m-%d %H:%M")
        rem_min = max(0, int(diff_sec // 60))
        if 0 < diff_sec <= 3600:
            end_display = f"北京时间 {end_dt_bjt} (仅剩 {rem_min} 分钟!)"
        else:
            end_display = f"北京时间 {end_dt_bjt} (剩余: {end_display})"
        return end_display, is_within_1h

    if re.search(r"^(\d+分|\d+秒)$", end_display):
        is_within_1h = True
    return end_display, is_within_1h


def extract_raw_products(html_text: str):
    """三引擎解析：兼容经典 li.Product、新版 __NEXT_DATA__ JSON、以及通用 /jp/auction/ 链接"""
    soup = BeautifulSoup(html_text, "html.parser")
    raw_items = []
    seen = set()

    # 引擎 1：经典 li.Product 节点
    for prod in soup.select("li.Product"):
        title_el = prod.select_one("a.Product__titleLink")
        price_el = prod.select_one("span.Product__priceValue")
        time_el = prod.select_one("span.Product__time")
        bonus_el = prod.select_one(".Product__bonus")
        if title_el and price_el:
            link = title_el.get("href", "").split("?")[0]
            if link and link not in seen:
                seen.add(link)
                raw_items.append({
                    "title": title_el.get_text(strip=True),
                    "price": price_el.get_text(strip=True),
                    "raw_time": time_el.get_text(strip=True) if time_el else "未知",
                    "end_ts_ms": bonus_el.get("data-auction-endtime") if bonus_el else None,
                    "link": link,
                })

    # 引擎 2：新版 Next.js 内嵌 JSON (__NEXT_DATA__)
    if not raw_items:
        next_script = soup.find("script", id="__NEXT_DATA__")
        if next_script and next_script.string:
            try:
                data = json.loads(next_script.string)
                def walk(node):
                    if isinstance(node, dict):
                        aid = node.get("auctionId") or node.get("id")
                        title = node.get("title")
                        price = node.get("price") or node.get("currentPrice") or node.get("buyNowPrice")
                        if aid and title and price is not None and re.match(r"^[a-zA-Z0-9]{8,15}$", str(aid)):
                            link = f"https://auctions.yahoo.co.jp/jp/auction/{aid}"
                            if link not in seen:
                                seen.add(link)
                                p_str = f"{int(price):,}円" if isinstance(price, (int, float)) else str(price)
                                raw_items.append({
                                    "title": str(title),
                                    "price": p_str,
                                    "raw_time": str(node.get("endTime") or "见详情页"),
                                    "end_ts_ms": None,
                                    "link": link,
                                })
                        for v in node.values():
                            walk(v)
                    elif isinstance(node, list):
                        for item in node:
                            walk(item)
                walk(data)
            except Exception:
                pass

    # 引擎 3：通用拍品链接兜底提取
    if not raw_items:
        for a_tag in soup.select('a[href*="/jp/auction/"]'):
            link = a_tag.get("href", "").split("?")[0]
            title = a_tag.get_text(strip=True)
            if not link or not title or len(title) < 6 or link in seen:
                continue
            parent = a_tag.find_parent(["li", "div"])
            p_text = parent.get_text(" ", strip=True) if parent else ""
            price_match = re.search(r"([\d,]+円)", p_text)
            time_match = re.search(r"(\d+日|\d+時間|\d+分|\d+秒)", p_text)
            seen.add(link)
            raw_items.append({
                "title": title,
                "price": price_match.group(1) if price_match else "价格见详情页",
                "raw_time": time_match.group(1) if time_match else "见详情页",
                "end_ts_ms": None,
                "link": link,
            })

    return raw_items


def fetch_yahoo_auctions(target: dict, mode: str = "auction"):
    url = "https://auctions.yahoo.co.jp/search/search"
    params = {
        "p": target["query"],
        "b": 1,
        "n": 40,
        "fixed": 2 if mode == "auction" else 1,
        "s1": "end" if mode == "auction" else "new",
        "o1": "a" if mode == "auction" else "d",
    }

    results = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        raw_items = extract_raw_products(resp.text)

        for item in raw_items:
            if not is_valid_item(item["title"], target):
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

        print(f"[诊断日志] {target['name']} ({mode}): 网页原始解析 {len(raw_items)} 条 -> 过滤后保留 {len(results)} 条")
    except Exception as e:
        print(f"[ERROR] 抓取 {target['name']} ({mode}) 失败: {e}")

    return results


def push_to_wechat(title: str, md_content: str):
    raw_tokens = os.getenv("PUSHPLUS_TOKEN", "")
    topic = os.getenv("PUSHPLUS_TOPIC", "").strip()
    tokens = [t.strip() for t in re.split(r"[,，\s]+", raw_tokens) if t.strip()]

    if not tokens:
        print("💡 未检测到 PUSHPLUS_TOKEN 环境变量，跳过微信推送。")
        return

    for idx, token in enumerate(tokens, 1):
        payload = {
            "token": token,
            "title": f"{title} #{idx}" if len(tokens) > 1 else title,
            "content": md_content,
            "template": "markdown",
        }
        if topic:
            payload["topic"] = topic
        try:
            r = requests.post("https://www.pushplus.plus/send", json=payload, timeout=15)
            print(f"[微信接收人 {idx} 推送状态]: {r.text}")
        except Exception as e:
            print(f"[微信接收人 {idx} 推送失败]: {e}")
        if len(tokens) > 1:
            time.sleep(3)


def main():
    now_str = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    urgent_auctions = []
    all_auctions = []
    all_fixed = []
    seen_links = set()

    for target in TARGETS:
        auctions = fetch_yahoo_auctions(target, mode="auction")
        for item in auctions:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                all_auctions.append(item)
                if item["within_1h"]:
                    urgent_auctions.append(item)
        time.sleep(1.2)

        fixed_items = fetch_yahoo_auctions(target, mode="fixed")
        for item in fixed_items:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                all_fixed.append(item)
        time.sleep(1.2)

    lines = [f"### 📡 雅虎拍卖相机监测 ({now_str} 北京时间)\n"]

    lines.append(f"#### 🚨 一、 距拍卖结束不足 1 小时的商品 ({len(urgent_auctions)}件)")
    if not urgent_auctions:
        lines.append("当前暂无 1 小时内结束的目标拍卖商品。\n")
    else:
        for i, it in enumerate(urgent_auctions, 1):
            lines.append(
                f"{i}. 🔥 **[{it['model']}]** | 价格: `{it['price']}`\n"
                f"   - 简介: {it['title']}\n"
                f"   - 结束时间: **{it['end_info']}**\n"
                f"   - 拍卖链接: [点击查看]({it['link']})\n"
            )

    lines.append(f"\n#### 🔨 二、 拍卖商品列表 ({len(all_auctions)}件)")
    if not all_auctions:
        lines.append("当前暂无符合条件的拍卖商品。\n")
    else:
        for i, it in enumerate(all_auctions[:25], 1):
            flag = "🔥[不足1小时] " if it["within_1h"] else ""
            lines.append(
                f"{i}. {flag}**[{it['model']}]** | 价格: `{it['price']}`\n"
                f"   - 简介: {it['title']}\n"
                f"   - 结束时间: {it['end_info']}\n"
                f"   - 拍卖链接: [点击查看]({it['link']})"
            )

    lines.append(f"\n#### 🛍️ 三、 定额在售商品列表 ({len(all_fixed)}件)")
    if not all_fixed:
        lines.append("当前暂无符合条件的定额在售商品。\n")
    else:
        for i, it in enumerate(all_fixed[:25], 1):
            lines.append(
                f"{i}. **[{it['model']}]** | 在售价: `{it['price']}`\n"
                f"   - 简介: {it['title']}\n"
                f"   - 在售链接: [点击查看]({it['link']})"
            )

    report_md = "\n".join(lines)
    print(report_md)

    if urgent_auctions:
        push_title = f"🚨【紧急! {len(urgent_auctions)}件不足1小时截标】日拍相机 ({now_str})"
    else:
        push_title = f"📷 日拍相机整点报告 ({now_str} | 竞拍{len(all_auctions)}件/在售{len(all_fixed)}件)"

    push_to_wechat(push_title, report_md)


if __name__ == "__main__":
    main()
