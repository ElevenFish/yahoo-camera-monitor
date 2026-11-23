#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
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
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://auctions.yahoo.co.jp/",
}

# ==================== 15 款监测相机配置（分两大类） ====================
TARGETS = [
    # --- 第一大类：高端便携胶片机 & 旁轴相机 (9款) ---
    {
        "category": "compact",
        "name": "尼康 Nikon 35Ti",
        "query": "Nikon 35Ti",
        "keywords": ["35ti", "35 ti"],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "category": "compact",
        "name": "尼康 Nikon 28Ti",
        "query": "Nikon 28Ti",
        "keywords": ["28ti", "28 ti"],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "category": "compact",
        "name": "理光 Ricoh GR1s",
        "query": "RICOH GR1s",
        "keywords": ["gr1s", "gr 1s"],
        "exclude_lenses": False,
        "custom_exclude": ["gr1v", "gr10", "gr21", "digital"],
    },
    {
        "category": "compact",
        "name": "奥林巴斯 Olympus μ[mju:]-I (初代定焦)",
        "query": "OLYMPUS μ 35mm F3.5",
        "keywords": ["μ", "mju", "ミュー"],
        "exclude_lenses": False,
        "custom_exclude": [
            "zoom", "ズーム", "μ-ii", "μ ii", "mju-ii", "mju ii", "μ2",
            "μ-iii", "μ iii", "mju-iii", "f2.8", "f/2.8", "digital", "デジタル",
            "70", "80", "105", "115", "120", "140", "170", "deluxe", "dlx"
        ],
    },
    {
        "category": "compact",
        "name": "康泰时 Contax T3",
        "query": "CONTAX T3",
        "keywords": ["t3"],
        "exclude_lenses": False,
        "custom_exclude": ["autoreflex", "t2", "tvs"],
    },
    {
        "category": "compact",
        "name": "康泰时 Contax G2",
        "query": "CONTAX G2",
        "keywords": ["g2"],
        "exclude_lenses": False,
        "custom_exclude": ["レンズのみ", "g1ボディ"],
    },
    {
        "category": "compact",
        "name": "美能达 Minolta TC-1",
        "query": "MINOLTA TC-1",
        "keywords": ["tc-1", "tc1"],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "category": "compact",
        "name": "柯尼卡 巧思 Konica HEXAR RF",
        "query": "Konica HEXAR RF",
        "keywords": ["hexar", "ヘキサー"],
        "exclude_lenses": False,
        "custom_exclude": ["レンズのみ", "hx-18wのみ"],
    },
    {
        "category": "compact",
        "name": "柯尼卡 巧思 Konica HEXAR AF",
        "query": "Konica HEXAR",
        "keywords": ["hexar", "ヘキサー"],
        "exclude_lenses": False,
        "custom_exclude": [
            "hexar rf", "ヘキサーrf", "ヘキサー rf", "m-hexanon",
            "pearl", "パール", "50mm", "75mm", "f3.5", "f4.5",
            "ストロボのみ", "フラッシュのみ", "hx-14のみ"
        ],
    },

    # --- 第二大类：中画幅 & 徕卡旁轴单机身-不含镜头 (6款) ---
    {
        "category": "body_only",
        "name": "哈苏 500CX / 503CX (不含镜头)",
        "query": "HASSELBLAD 503CX",
        "keywords": ["503cx", "500cx"],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "category": "body_only",
        "name": "哈苏 500C/M (不含镜头)",
        "query": "HASSELBLAD 500C/M",
        "keywords": ["500c/m", "500cm", "500 c/m"],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "category": "body_only",
        "name": "哈苏 503CW (不含镜头)",
        "query": "HASSELBLAD 503CW",
        "keywords": ["503cw"],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "category": "body_only",
        "name": "徕卡 M6 复刻版 (不含镜头)",
        "query": "Leica M6 復刻",
        "keywords": ["m6"],
        "exclude_lenses": True,
        "custom_exclude": ["ttl", "チタン", "titan"],
    },
    {
        "category": "body_only",
        "name": "徕卡 M6 Ti 钛版 (不含镜头)",
        "query": "Leica M6 チタン",
        "keywords": ["m6"],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "category": "body_only",
        "name": "康泰时 Contax 645 全套 (不含镜头)",
        "query": "CONTAX 645",
        "keywords": ["645"],
        "exclude_lenses": True,
        "custom_exclude": ["pentax", "mamiya", "bronica"],
    },
]

# 仅排除明确的杂志、目录、纯说明书、空箱、扭蛋摆件（绝不包含单字"本"，防止误杀"本体"）
SAFE_JUNK_EXCLUDE = [
    "雑誌", "ムック", "mook", "カタログ", "パンフレット",
    "取扱説明書", "使用説明書", "取説のみ",
    "空箱", "元箱のみ", "箱のみ", "キャップのみ", "ケースのみ", "ストラップのみ",
    "ガチャ", "ガシャポン", "ミニチュア", "クリスタル", "置物"
]

# 仅针对「不含镜头」单机身目标 (exclude_lenses=True) 排除镜头套装
LENS_EXCLUDE_KEYWORDS = [
    "レンズセット", "レンズ付", "レンズつき", "+レンズ", "＋レンズ",
    "planar", "distagon", "sonnar", "biogon", "summicron", "summilux", "elmarit",
    "80mm", "2.8/80",
]


def http_get(url: str, params: dict = None):
    if USE_CFFI:
        return cffi_requests.get(
            url, params=params, headers=HEADERS, impersonate="chrome120", timeout=20
        )
    return requests.get(url, params=params, headers=HEADERS, timeout=20)


def is_valid_item(title: str, target: dict) -> bool:
    t_lower = title.lower()

    # 1. 型号关键词匹配
    if target.get("keywords") and not any(k in t_lower for k in target["keywords"]):
        return False

    # 2. 安全排除明确书刊/空箱/玩具
    for bad in SAFE_JUNK_EXCLUDE:
        if bad in t_lower:
            return False

    # 3. 机型防串号排除
    for c_bad in target.get("custom_exclude", []):
        if c_bad in t_lower:
            return False

    # 4. 单机身机型排除镜头套装
    if target.get("exclude_lenses", False):
        for l_bad in LENS_EXCLUDE_KEYWORDS:
            if l_bad in t_lower:
                return False

    return True


def parse_remaining_time(time_str: str, end_timestamp_ms=None):
    is_within_1h = False
    end_display = str(time_str).strip() if time_str else "进行中"

    if end_timestamp_ms:
        ts_val = str(end_timestamp_ms).strip()
        if ts_val.isdigit():
            # 兼容秒级(10位)和毫秒级(13位)时间戳
            end_ts = int(ts_val) / 1000.0 if len(ts_val) > 11 else float(ts_val)
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


def extract_from_next_data(soup: BeautifulSoup):
    """层 1：从雅虎新版 React/Next.js 页面的 __NEXT_DATA__ JSON 中提取拍品"""
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return []

    items = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            # 寻找包含 auctionId 与 title 的拍品字典
            aid = node.get("auctionId") or node.get("id")
            title = node.get("title") or node.get("name")
            price = node.get("currentPrice") or node.get("price") or node.get("bidOrBuy")
            if (
                isinstance(aid, str)
                and re.match(r"^[a-zA-Z0-9]{8,16}$", aid)
                and isinstance(title, str)
                and len(title) >= 3
                and price is not None
                and aid not in seen
            ):
                seen.add(aid)
                price_num = re.sub(r"[^\d]", "", str(price))
                price_fmt = f"{int(price_num):,}円" if price_num else str(price)
                bids = node.get("bidCount") or node.get("bids") or 0
                end_time = node.get("endTime") or node.get("remainingTime") or "进行中"
                items.append({
                    "title": title.strip(),
                    "link": f"https://auctions.yahoo.co.jp/jp/auction/{aid}",
                    "price": price_fmt,
                    "bids": f"{bids}次出价" if bids else "",
                    "raw_time": str(end_time),
                    "end_ts_ms": end_time if str(end_time).isdigit() else None,
                })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for el in node:
                walk(el)

    try:
        data = json.loads(script_tag.string)
        walk(data)
    except Exception:
        pass
    return items


def parse_yahoo_html(html_text: str, target: dict):
    """三层联合解析雅虎拍卖页面：JSON -> 经典 li.Product -> 拍品链接反查"""
    soup = BeautifulSoup(html_text, "html.parser")
    raw_items = extract_from_next_data(soup)

    # 层 2：经典 li.Product 节点
    if not raw_items:
        for prod in soup.select("li.Product"):
            title_el = prod.select_one("a.Product__titleLink")
            price_el = prod.select_one("span.Product__priceValue")
            time_el = prod.select_one("span.Product__time")
            bid_el = prod.select_one("span.Product__bid")
            bonus_el = prod.select_one(".Product__bonus")
            if not title_el or not price_el:
                continue
            bid_txt = bid_el.get_text(strip=True) if bid_el else ""
            raw_items.append({
                "title": title_el.get_text(strip=True),
                "link": title_el.get("href", "").split("?")[0],
                "price": price_el.get_text(strip=True),
                "bids": f"{bid_txt}次出价" if bid_txt.isdigit() and int(bid_txt) > 0 else "",
                "raw_time": time_el.get_text(strip=True) if time_el else "进行中",
                "end_ts_ms": bonus_el.get("data-auction-endtime") if bonus_el else None,
            })

    # 层 3：通用 /jp/auction/ 链接扫描反查父节点
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

            bid_match = re.search(r"入札\s*(\d+)", block_text)
            bid_str = f"{bid_match.group(1)}次出价" if bid_match and int(bid_match.group(1)) > 0 else ""

            full_link = href if href.startswith("http") else f"https://auctions.yahoo.co.jp{href}"
            raw_items.append({
                "title": title_text,
                "link": full_link,
                "price": price_str,
                "bids": bid_str,
                "raw_time": time_str,
                "end_ts_ms": None,
            })

    results = []
    for item in raw_items:
        if not is_valid_item(item["title"], target):
            continue
        end_info, within_1h = parse_remaining_time(item["raw_time"], item.get("end_ts_ms"))
        results.append({
            "model": target["name"],
            "title": item["title"],
            "price": item["price"],
            "bids": item.get("bids", ""),
            "end_info": end_info,
            "within_1h": within_1h,
            "link": item["link"],
        })

    return len(raw_items), results


def fetch_zenmarket_fallback(target: dict):
    """当雅虎主站在海外机房 IP 下返回 0 条时，通过 ZenMarket 日拍镜像抓同源实时数据"""
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

            if not is_valid_item(title, target):
                continue

            container = a_tag.find_parent("div", class_=re.compile(r"product|item|card", re.I)) or a_tag.find_parent("div")
            block_text = container.get_text(" ", strip=True) if container else ""
            price_match = re.search(r"(?:¥|JPY\s*)([\d,]+)|([\d,]+)\s*(?:円|JPY)", block_text, re.I)
            price_str = f"{price_match.group(1) or price_match.group(2)}円" if price_match else "详见链接"

            results.append({
                "model": target["name"],
                "title": title,
                "price": price_str,
                "bids": "",
                "end_info": "日拍实时在拍",
                "within_1h": False,
                "link": f"https://auctions.yahoo.co.jp/jp/auction/{aid}",
            })
    except Exception as e:
        print(f"  [ZenMarket 兜底异常] {target['name']}: {e}")

    return raw_count, results


def fetch_yahoo_by_path(target: dict, mode: str = "auction"):
    """
    使用雅虎拍卖最新路径式检索地址:
    https://auctions.yahoo.co.jp/search/search/{encoded_query}/0
    """
    encoded_q = urllib.parse.quote(target["query"])
    url = f"https://auctions.yahoo.co.jp/search/search/{encoded_q}/0"
    params = {
        "b": "1",
        "n": "50",
    }
    if mode == "auction":
        params["fixed"] = "2"  # 竞拍 (オークション)
        params["s1"] = "end"
        params["o1"] = "a"
    else:
        params["fixed"] = "1"  # 定额一口价 (定額/即決)
        params["s1"] = "new"
        params["o1"] = "d"

    try:
        resp = http_get(url, params=params)
        raw_count, results = parse_yahoo_html(resp.text, target)
        print(f"[{target['name']} - {mode}] HTTP {resp.status_code} | 原始 {raw_count} 条 -> 有效 {len(results)} 条")

        # 若主站返回 0 条，在 auction 模式下启用 ZenMarket 镜像兜底
        if raw_count == 0 and mode == "auction":
            z_raw, z_res = fetch_zenmarket_fallback(target)
            print(f"  ↳ [ZenMarket 镜像兜底] {target['name']}: 原始 {z_raw} 条 -> 有效 {len(z_res)} 条")
            return z_res

        return results
    except Exception as e:
        print(f"[ERROR] 抓取 {target['name']} ({mode}) 异常: {e}")
        if mode == "auction":
            _, z_res = fetch_zenmarket_fallback(target)
            return z_res
        return []


def format_model_section(idx: int, model_info: dict) -> str:
    """将单款相机格式化为与标准清单一致的明细段落"""
    name = model_info["name"]
    search_url = model_info["search_url"]
    auctions = model_info["auctions"]
    fixed_items = model_info["fixed"]

    sec = [
        f"#### {idx}. {name}",
        f"在拍 **{len(auctions)}** 件 / 定额 **{len(fixed_items)}** 件 ｜ [👉 雅虎实时检索页]({search_url})"
    ]

    if not auctions and not fixed_items:
        sec.append("- 当前暂无直接抓取到的明细，可点击上方检索页直达雅虎查看。\n")
        return "\n".join(sec)

    # 展示该机型前 4 条竞拍商品
    for it in auctions[:4]:
        urgent_tag = "🔥**[不足1小时]** " if it["within_1h"] else ""
        bid_part = f"（{it['bids']}）" if it["bids"] else ""
        sec.append(
            f"- {urgent_tag}**[竞拍]** `{it['price']}`{bid_part} ｜ 结束: **{it['end_info']}**\n"
            f"  {it['title']} — [拍卖链接]({it['link']})"
        )

    # 展示该机型前 4 条定额在售商品
    for it in fixed_items[:4]:
        sec.append(
            f"- **[定额/一口价]** `{it['price']}`\n"
            f"  {it['title']} — [在售链接]({it['link']})"
        )

    sec.append("")  # 空行分隔
    return "\n".join(sec)


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
        print(f"正在向第 {idx} 个微信发送推送 (Token: {masked})...")
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
    compact_models = []
    body_models = []
    total_auction_count = 0
    total_fixed_count = 0

    for target in TARGETS:
        encoded_q = urllib.parse.quote(target["query"])
        search_url = f"https://auctions.yahoo.co.jp/search/search/{encoded_q}/0"

        auctions = fetch_yahoo_by_path(target, mode="auction")
        time.sleep(0.5)
        fixed_items = fetch_yahoo_by_path(target, mode="fixed")
        time.sleep(0.5)

        total_auction_count += len(auctions)
        total_fixed_count += len(fixed_items)

        for it in auctions:
            if it["within_1h"]:
                urgent_auctions.append(it)

        model_data = {
            "name": target["name"],
            "search_url": search_url,
            "auctions": auctions,
            "fixed": fixed_items,
        }
        if target["category"] == "compact":
            compact_models.append(model_data)
        else:
            body_models.append(model_data)

    # ---------------- 组装第一部分：紧急截标 + 9款高端便携机/旁轴 ----------------
    part1_lines = [
        f"### 📡 雅虎拍卖 15 款相机实时全量清单 ({now_str} 北京时间)",
        f"本次共检索到竞拍 **{total_auction_count}** 件、定额在售 **{total_fixed_count}** 件\n",
        f"### 🚨 一、 重点关注：距结束不足 1 小时的竞拍 ({len(urgent_auctions)} 件)",
    ]
    if not urgent_auctions:
        part1_lines.append("> 当前暂无 1 小时内截标的目标机型。\n")
    else:
        for i, it in enumerate(urgent_auctions, 1):
            part1_lines.append(
                f"{i}. 🔥 **[{it['model']}]** `{it['price']}` ｜ 结束: **{it['end_info']}**\n"
                f"   {it['title']} — [👉 立即前往竞拍]({it['link']})\n"
            )

    part1_lines.append("### 📸 二、 高端便携胶片机 & 旁轴相机（9 款实时清单）\n")
    for idx, m in enumerate(compact_models, 1):
        part1_lines.append(format_model_section(idx, m))

    # ---------------- 组装第二部分：6款中画幅 & 徕卡单机身 ----------------
    part2_lines = ["### 🎞️ 三、 中画幅 & 徕卡旁轴单机身（不含镜头，6 款实时清单）\n"]
    for idx, m in enumerate(body_models, 1):
        part2_lines.append(format_model_section(idx, m))

    part1_md = "\n".join(part1_lines)
    part2_md = "\n".join(part2_lines)
    full_md = part1_md + "\n" + part2_md

    print("\n" + full_md)

    # 动态标题
    if urgent_auctions:
        base_title = f"🚨【紧急! {len(urgent_auctions)}件1小时内截标】日拍15款相机清单 ({now_str})"
    else:
        base_title = f"📷 日拍15款相机清单 ({now_str} | 拍{total_auction_count}/售{total_fixed_count})"

    # 若合并内容超过 9000 字符，自动分上下两篇推送，防止微信卡片过长被截断
    if len(full_md) > 9000:
        push_to_wechat(f"{base_title} [1/2 便携与旁轴]", part1_md)
        time.sleep(1.5)
        push_to_wechat(f"{base_title} [2/2 中画幅与徕卡]", part2_md)
    else:
        push_to_wechat(base_title, full_md)


if __name__ == "__main__":
    main()
