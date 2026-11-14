#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

# 设定北京时间时区 (UTC+8)
BJT = pytz.timezone("Asia/Shanghai")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# ==================== 1. 监测目标配置（仅机身/不含镜头） ====================
TARGETS = [
    {
        "name": "哈苏 500CX / 503CX",
        "query": "HASSELBLAD 503CX ボディ",
        "must_include_any": ["503cx", "500cx"],
        "must_include_all": [],
    },
    {
        "name": "哈苏 500C/M",
        "query": "HASSELBLAD 500C/M ボディ",
        "must_include_any": ["500c/m", "500cm"],
        "must_include_all": [],
    },
    {
        "name": "哈苏 503CW",
        "query": "HASSELBLAD 503CW ボディ",
        "must_include_any": ["503cw"],
        "must_include_all": [],
    },
    {
        "name": "徕卡 M6 复刻版 (10557)",
        "query": "Leica M6 復刻 OR 10557 ボディ",
        "must_include_any": ["m6"],
        "must_include_all": [],
    },
    {
        "name": "徕卡 M6 Ti (钛版)",
        "query": "Leica M6 チタン OR TITAN ボディ",
        "must_include_any": ["チタン", "titan"],
        "must_include_all": ["m6"],
    },
    {
        "name": "康泰时 Contax 645 全套(不含镜头)",
        "query": "CONTAX 645 ボディ MF-1 MFB-1",
        "must_include_any": ["mf-1", "mfb-1", "kit", "セット"],
        "must_include_all": ["645"],
    },
]

# 排除关键词：剔除含镜头套装、纯零配件及故障零件机
EXCLUDE_KEYWORDS = [
    "レンズセット", "レンズ付", "レンズつき", "+レンズ", "＋レンズ",
    "planar", "distagon", "sonnar", "biogon", "summicron", "summilux", "elmarit",
    "80mm", "50mm", "35mm", "45mm", "f2.8", "f/2.8", "2.8/80",
    "スクリーン", "キャップのみ", "空箱", "説明書のみ", "ストラップのみ", "ジャンク品"
]


# ==================== 2. 过滤与时间解析模块 ====================

def is_valid_item(title: str, target: dict) -> bool:
    """检查商品标题是否符合单机身/无镜头全套要求"""
    t_lower = title.lower()
    if target["must_include_any"] and not any(k in t_lower for k in target["must_include_any"]):
        return False
    for k in target["must_include_all"]:
        if k not in t_lower:
            return False
    for bad_word in EXCLUDE_KEYWORDS:
        if bad_word in t_lower:
            return False
    return True


def parse_remaining_time(time_str: str, end_timestamp_ms: str = None):
    """
    解析雅虎拍卖结束时间并判断是否距离结束不足 1 小时 (3600秒)
    返回: (格式化结束时间字符串, 是否不足1小时布尔值)
    """
    is_within_1h = False
    end_display = time_str.strip()

    # 优先读取雅虎拍卖精确到毫秒的截标时间戳
    if end_timestamp_ms and end_timestamp_ms.isdigit():
        end_ts = int(end_timestamp_ms) / 1000.0
        diff_sec = end_ts - time.time()
        if 0 < diff_sec <= 3600:
            is_within_1h = True
        end_dt_bjt = datetime.fromtimestamp(end_ts, BJT).strftime("%m-%d %H:%M")
        rem_min = max(0, int(diff_sec // 60))
        if 0 < diff_sec <= 3600:
            end_display = f"北京时间 {end_dt_bjt} (仅剩 {rem_min} 分钟!)"
        else:
            end_display = f"北京时间 {end_dt_bjt} (剩余: {time_str.strip()})"
        return end_display, is_within_1h

    # 备用文本解析：若日拍直接显示 "XX分" 或 "XX秒" 则代表不足1小时
    if re.search(r"^(\d+分|\d+秒)$", end_display):
        is_within_1h = True
    return end_display, is_within_1h


# ==================== 3. 雅虎拍卖数据抓取模块 ====================

def fetch_yahoo_auctions(target: dict, mode: str = "auction"):
    """
    mode='auction' -> 抓取竞拍商品 (fixed=2)，按结束时间从近到远排序 (s1=end&o1=a)
    mode='fixed'   -> 抓取定额在售商品 (fixed=1)，按最新上架排序 (s1=new&o1=d)
    """
    url = "https://auctions.yahoo.co.jp/search/search"
    params = {
        "p": target["query"],
        "va": target["query"],
        "ve": "レンズセット Planar Distagon Summicron キャップのみ",
        "b": 1,
        "n": 30,
    }
    if mode == "auction":
        params["fixed"] = 2
        params["s1"] = "end"
        params["o1"] = "a"
    else:
        params["fixed"] = 1
        params["s1"] = "new"
        params["o1"] = "d"

    results = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for prod in soup.select("li.Product"):
            title_el = prod.select_one("a.Product__titleLink")
            price_el = prod.select_one("span.Product__priceValue")
            time_el = prod.select_one("span.Product__time")
            bonus_el = prod.select_one(".Product__bonus")

            if not title_el or not price_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "").split("?")[0]
            price = price_el.get_text(strip=True)

            if not is_valid_item(title, target):
                continue

            end_ts_ms = bonus_el.get("data-auction-endtime") if bonus_el else None
            raw_time = time_el.get_text(strip=True) if time_el else "未知"
            end_info, within_1h = parse_remaining_time(raw_time, end_ts_ms)

            results.append({
                "model": target["name"],
                "title": title,
                "price": price,
                "end_info": end_info,
                "within_1h": within_1h,
                "link": link,
            })
    except Exception as e:
        print(f"[ERROR] 抓取 {target['name']} ({mode}) 失败: {e}")

    return results


# ==================== 4. 双人/多人微信推送模块 ====================

def push_to_wechat(title: str, md_content: str):
    """
    支持同时向 2 个或更多微信号发送报告：
    只需在 GitHub Secrets 的 PUSHPLUS_TOKEN 中用英文逗号分隔多个 Token 即可。
    同时也兼容可选的 PUSHPLUS_TOPIC 群组编码模式。
    """
    raw_tokens = os.getenv("PUSHPLUS_TOKEN", "")
    topic = os.getenv("PUSHPLUS_TOPIC", "").strip()
    tokens = [t.strip() for t in re.split(r"[,，\s]+", raw_tokens) if t.strip()]

    if not tokens:
        print("💡 未检测到 PUSHPLUS_TOKEN 环境变量，跳过微信推送。")
        return

    for idx, token in enumerate(tokens, 1):
        payload = {
            "token": token,
            "title": title,
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


# ==================== 5. 主程序与报告排版 ====================

def main():
    now_str = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    urgent_auctions = []
    all_auctions = []
    all_fixed = []
    seen_links = set()

    for target in TARGETS:
        # 1. 检索竞拍商品
        auctions = fetch_yahoo_auctions(target, mode="auction")
        for item in auctions:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                all_auctions.append(item)
                if item["within_1h"]:
                    urgent_auctions.append(item)
        time.sleep(1.0)

        # 2. 检索定额在售商品
        fixed_items = fetch_yahoo_auctions(target, mode="fixed")
        for item in fixed_items:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                all_fixed.append(item)
        time.sleep(1.0)

    # 组装 Markdown 报告内容
    lines = [f"### 📡 雅虎拍卖相机监测 ({now_str} 北京时间)\n"]

    # 第一板块：距离结束不足 1 小时的紧急竞拍商品
    lines.append(f"#### 🚨 一、 距拍卖结束不足 1 小时的商品 ({len(urgent_auctions)}件)")
    if not urgent_auctions:
        lines.append("当前暂无 1 小时内结束的目标拍卖商品。\n")
    else:
        for i, it in enumerate(urgent_auctions, 1):
            lines.append(
                f"{i}. 🔥 **[{it['model']}]**\n"
                f"   - **当前价格**: `{it['price']}`\n"
                f"   - **商品简介**: {it['title']}\n"
                f"   - **结束时间**: **{it['end_info']}**\n"
                f"   - **拍卖链接**: [点击直达雅虎拍卖页]({it['link']})\n"
            )

    # 第二板块：全部在拍商品列表
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

    # 第三板块：定额在售商品列表
    lines.append(f"\n#### 🛍️ 三、 定额在售商品列表 ({len(all_fixed)}件)")
    if not all_fixed:
        lines.append("当前暂无符合条件的定额在售商品。\n")
    else:
        for i, it in enumerate(all_fixed[:25], 1):
            lines.append(
                f"{i}. **[{it['model']}]** | 在售价格: `{it['price']}`\n"
                f"   - 简介: {it['title']}\n"
                f"   - 在售链接: [点击查看]({it['link']})"
            )

    report_md = "\n".join(lines)
    print(report_md)

    # 设置微信卡片标题
    if urgent_auctions:
        push_title = f"🚨【紧急! {len(urgent_auctions)}件不足1小时截标】日拍相机 ({now_str})"
    else:
        push_title = f"📷 日拍相机整点报告 ({now_str} | 竞拍{len(all_auctions)}件)"

    push_to_wechat(push_title, report_md)


if __name__ == "__main__":
    main()
