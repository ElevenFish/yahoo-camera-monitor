#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

# 设置北京时间时区
BJT = pytz.timezone("Asia/Shanghai")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 雅虎拍卖「胶片相机 (フィルムカメラ)」分类 ID
YAHOO_FILM_CAMERA_CATEGORY_ID = "23640"

# ==================== 15 款监测相机配置 ====================
TARGETS = [
    # --- 1~6：中画幅与旁轴单机身（不含镜头） ---
    {
        "name": "哈苏 500CX / 503CX (不含镜头)",
        "query": "HASSELBLAD 503CX",
        "must_include_any": ["503cx", "500cx"],
        "must_include_all": [],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "name": "哈苏 500C/M (不含镜头)",
        "query": "HASSELBLAD 500C/M",
        "must_include_any": ["500c/m", "500cm"],
        "must_include_all": [],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "name": "哈苏 503CW (不含镜头)",
        "query": "HASSELBLAD 503CW",
        "must_include_any": ["503cw"],
        "must_include_all": [],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "name": "徕卡 M6 复刻版 (10557)",
        "query": "Leica M6",
        "must_include_any": ["復刻", "10557", "2022", "ライカ m6 ボディ", "leica m6 body"],
        "must_include_all": ["m6"],
        "exclude_lenses": True,
        "custom_exclude": ["ttl", "チタン", "titan", "ジャンク"],
    },
    {
        "name": "徕卡 M6 Ti (钛版)",
        "query": "Leica M6 チタン",
        "must_include_any": ["チタン", "titan"],
        "must_include_all": ["m6"],
        "exclude_lenses": True,
        "custom_exclude": [],
    },
    {
        "name": "康泰时 Contax 645 (不含镜头)",
        "query": "CONTAX 645 ボディ",
        "must_include_any": ["mf-1", "mfb-1", "kit", "セット", "ボディ", "body"],
        "must_include_all": ["645"],
        "exclude_lenses": True,
        "custom_exclude": ["pentax", "mamiya", "bronica", "fuji"],
    },

    # --- 7~15：高端便携胶片机 & 旁轴相机 ---
    {
        "name": "尼康 Nikon 35Ti",
        "query": "Nikon 35Ti",
        "must_include_any": ["35ti", "35 ti"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "name": "尼康 Nikon 28Ti",
        "query": "Nikon 28Ti",
        "must_include_any": ["28ti", "28 ti"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "name": "理光 Ricoh GR1s",
        "query": "RICOH GR1s",
        "must_include_any": ["gr1s", "gr 1s"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": ["gr1v", "gr10", "gr21", "digital"],
    },
    {
        "name": "奥林巴斯 Olympus μ[mju:]-I (初代)",
        "query": "OLYMPUS μ 35mm F3.5",
        "must_include_any": ["μ", "mju", "ミュー"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": [
            "zoom", "ズーム", "μ-ii", "μ ii", "mju-ii", "mju ii", "μ2",
            "μ-iii", "μ iii", "mju-iii", "f2.8", "f/2.8", "digital", "デジタル",
            "70", "80", "105", "115", "120", "140", "170", "deluxe", "dlx"
        ],
    },
    {
        "name": "康泰时 Contax T3",
        "query": "CONTAX T3",
        "must_include_any": ["t3"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": ["autoreflex", "t2", "tvs"],
    },
    {
        "name": "康泰时 Contax G2",
        "query": "CONTAX G2",
        "must_include_any": ["g2"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": ["レンズのみ", "g1ボディ"],
    },
    {
        "name": "美能达 Minolta TC-1",
        "query": "MINOLTA TC-1",
        "must_include_any": ["tc-1", "tc1"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": [],
    },
    {
        "name": "柯尼卡 巧思 Konica HEXAR RF",
        "query": "Konica HEXAR RF",
        "must_include_any": ["hexar", "ヘキサー"],
        "must_include_all": ["rf"],
        "exclude_lenses": False,
        "custom_exclude": ["レンズのみ", "hx-18wのみ"],
    },
    {
        "name": "柯尼卡 巧思 Konica HEXAR AF",
        "query": "Konica HEXAR",
        "must_include_any": ["hexar", "ヘキサー"],
        "must_include_all": [],
        "exclude_lenses": False,
        "custom_exclude": [
            "hexar rf", "ヘキサーrf", "ヘキサー rf", "m-hexanon",
            "pearl", "パール", "50mm", "75mm", "f3.5", "f4.5",
            "ストロボのみ", "フラッシュのみ", "hx-14のみ"
        ],
    },
]

# 全局排除词：严格滤除杂志、书籍、画册、说明书、纯配件、空盒、扭蛋模型
# 注意：绝不能写单字 "本"，否则会误杀含「本体」「日本製」「基本動作」的正常相机
BOOK_AND_JUNK_EXCLUDE = [
    "雑誌", "ムック", "mook", "書籍", "古本", "単行本", "教本", "カタログ", "パンフレット", "パンフ",
    "説明書", "取扱説明書", "使用説明書", "取説", "マニュアル", "ガイドブック",
    "写真集", "ポスター", "切り抜き", "チラシ", "広告", "ブローシャー", "冊子",
    "アサヒカメラ", "日本カメラ", "カメラ毎日",
    "キャップのみ", "ケースのみ", "ソフトケースのみ", "ストラップのみ", "フードのみ",
    "空箱", "元箱のみ", "箱のみ", "木箱のみ",
    "ガチャ", "ガシャポン", "ミニチュア", "フィギュア", "ピンバッジ", "キーホルダー",
    "モックアップ"
]

# 仅针对「不含镜头」单机身目标 (exclude_lenses=True) 的镜头排除词
LENS_EXCLUDE_KEYWORDS = [
    "レンズセット", "レンズ付", "レンズつき", "+レンズ", "＋レンズ",
    "planar", "distagon", "sonnar", "biogon", "summicron", "summilux", "elmarit",
    "80mm", "f2.8", "f/2.8", "2.8/80",
]


def is_valid_item(title: str, target: dict) -> bool:
    t_lower = title.lower()

    if target["must_include_any"] and not any(k in t_lower for k in target["must_include_any"]):
        return False

    for k in target["must_include_all"]:
        if k not in t_lower:
            return False

    for bad_word in BOOK_AND_JUNK_EXCLUDE:
        if bad_word in t_lower:
            return False

    for custom_bad in target.get("custom_exclude", []):
        if custom_bad in t_lower:
            return False

    if target.get("exclude_lenses", False):
        for lens_word in LENS_EXCLUDE_KEYWORDS:
            if lens_word in t_lower:
                return False

    return True


def parse_remaining_time(time_str: str, end_timestamp_ms: str = None):
    is_within_1h = False
    end_display = time_str.strip()

    if end_timestamp_ms and end_timestamp_ms.isdigit():
        end_ts = int(end_timestamp_ms) / 1000.0
        diff_sec = end_ts - time.time()
        if 0 < diff_sec <= 3600:
            is_within_1h = True
        end_dt_bjt = datetime.fromtimestamp(end_ts, BJT).strftime("%m-%d %H:%M")
        rem_min = max(0, int(diff_sec // 60))
        if 0 < diff_sec <= 3600:
            end_display = f"{end_dt_bjt} (仅剩 {rem_min} 分钟!)"
        else:
            end_display = f"{end_dt_bjt} ({time_str.strip()})"
        return end_display, is_within_1h

    if re.search(r"^(\d+分|\d+秒)$", end_display):
        is_within_1h = True
    return end_display, is_within_1h


def fetch_yahoo_auctions(target: dict, mode: str = "auction"):
    url = "https://auctions.yahoo.co.jp/search/search"
    params = {
        "p": target["query"],
        "auccat": YAHOO_FILM_CAMERA_CATEGORY_ID,
        "b": 1,
        "n": 50,
    }
    if mode == "auction":
        params["fixed"] = 2  # 竞拍
        params["s1"] = "end"
        params["o1"] = "a"
    else:
        params["fixed"] = 1  # 定额一口价
        params["s1"] = "new"
        params["o1"] = "d"

    results = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        raw_products = soup.select("li.Product")
        for prod in raw_products:
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
        print(f"[{target['name']} - {mode}] 网页抓取 {len(raw_products)} 条 -> 过滤后保留 {len(results)} 条")
    except Exception as e:
        print(f"[ERROR] 抓取 {target['name']} ({mode}) 失败: {e}")

    return results


def build_markdown_report(now_str: str, urgent_auctions: list, all_auctions: list, all_fixed: list) -> str:
    lines = [
        f"### 📡 雅虎拍卖 15 款相机监测 ({now_str} 北京时间)",
        "已锁定「フィルムカメラ」分类并滤除杂志、书籍、画册、说明书及纯配件\n",
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

    lines.append(f"\n#### 🔨 二、 在拍商品列表 (共 {len(all_auctions)} 件，展示前 25 件)")
    if not all_auctions:
        lines.append("当前暂无符合条件的在拍商品。\n")
    else:
        for it in all_auctions[:25]:
            tag = "🔥" if it["within_1h"] else "•"
            lines.append(
                f"{tag} **[{it['model']}]** `{it['price']}` | 结束: {it['end_info']}\n"
                f"  {it['title']} — [拍卖链接]({it['link']})"
            )

    lines.append(f"\n#### 🛍️ 三、 定额在售商品 (共 {len(all_fixed)} 件，展示前 25 件)")
    if not all_fixed:
        lines.append("当前暂无符合条件的定额在售商品。\n")
    else:
        for it in all_fixed[:25]:
            lines.append(
                f"• **[{it['model']}]** 在售价: `{it['price']}`\n"
                f"  {it['title']} — [在售链接]({it['link']})"
            )

    return "\n".join(lines)


def push_to_wechat(title: str, md_content: str):
    """
    支持单人或双人/多人微信推送：
    1. 可在 PUSHPLUS_TOKEN 中用英文逗号分隔填入两个 Token（如 token1,token2）
    2. 或分别设置 PUSHPLUS_TOKEN 和 PUSHPLUS_TOKEN_2 环境变量
    """
    raw_tokens = os.getenv("PUSHPLUS_TOKEN", "")
    token_2 = os.getenv("PUSHPLUS_TOKEN_2", "")
    combined = f"{raw_tokens},{token_2}"

    # 拆分并清理所有空白字符、引号
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
        time.sleep(0.6)

        fixed_items = fetch_yahoo_auctions(target, mode="fixed")
        for item in fixed_items:
            if item["link"] not in seen_fixed_links:
                seen_fixed_links.add(item["link"])
                all_fixed.append(item)
        time.sleep(0.6)

    report_md = build_markdown_report(now_str, urgent_auctions, all_auctions, all_fixed)
    print("\n" + report_md)

    if urgent_auctions:
        push_title = f"🚨【紧急! {len(urgent_auctions)}件1小时内截标】15款日拍相机 ({now_str})"
    else:
        push_title = f"📷 日拍15款相机整点监测 ({now_str} | 在拍{len(all_auctions)}件)"

    push_to_wechat(push_title, report_md)


if __name__ == "__main__":
    main()
