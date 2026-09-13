#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 k34h → ccca 抓取当前有效域名，写入 Gist"""

import os
import re
import json
import urllib.request
from playwright.sync_api import sync_playwright

# ============ 配置 ============
K34H_ENTRY = "http://k34h.com/enter/index.html"

# GitHub Gist 配置（从环境变量读）
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")

# 已知兜底域名
FALLBACK = ["ap6a.com", "mv5s.com", "nja5.com"]

# 黑名单（噪音域名）
BLACKLIST = [
    "w3.org", "w3c.org", "microsoft.com", "google.com",
    "googleapis.com", "gstatic.com", "github.com",
    "jsdelivr.net", "cloudflare.com", "k34h.com",
    "jxbyte.com", "telegram.org", "schema.org",
    "example.com", "facebook.com", "twitter.com",
]


def log(msg):
    print(f"[fetch] {msg}")


def fetch_via_playwright():
    """用 Playwright 抓取真实域名"""
    domains = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        # 隐藏 webdriver 特征
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        page = ctx.new_page()

        try:
            log(f"打开入口: {K34H_ENTRY}")
            # ★ 用 domcontentloaded，不等 networkidle
            page.goto(K34H_ENTRY, wait_until="domcontentloaded", timeout=60000)
            # 等 JS 跳转完成
            page.wait_for_timeout(3000)

            final_url = page.url
            html = page.content()
            log(f"最终 URL: {final_url}")
            log(f"页面长度: {len(html)}")

            # 如果长度太小，可能是空壳，再等一会
            if len(html) < 500:
                log("页面太短，再等 5 秒")
                page.wait_for_timeout(5000)
                html = page.content()
                final_url = page.url
                log(f"重试后 URL: {final_url}")
                log(f"重试后长度: {len(html)}")

            # 打印前 500 字（诊断用）
            log(f"页面内容前 500 字:")
            log(html[:500])

            # 抠 var domain
            m = re.search(r"var\s+domain\s*[=:]\s*['\"]([^'\"]+)['\"]", html)
            if m:
                raw = m.group(1).replace("\\r", " ").replace("\\n", " ").replace("\\t", " ")
                for token in raw.split():
                    token = token.strip()
                    if token and "." in token and "/" not in token:
                        domains.append(token)
                        log(f"  var domain: {token}")

            # 抠 header_title
            m = re.search(r'id="header_title"[^>]*>([\s\S]*?)</span>', html, re.I)
            if m:
                raw = re.sub(r"<br\s*/?>", " ", m.group(1), flags=re.I)
                for token in raw.split():
                    token = token.strip()
                    if token and "." in token and "/" not in token:
                        domains.append(token)
                        log(f"  header_title: {token}")

            # 扫所有域名
            for d in re.findall(r"[a-z0-9-]+\.[a-z0-9-]+\.(?:com|net|xyz|cc|vip|top|club|site|online|org|io|me)", html, re.I):
                d = d.lower()
                if not any(b in d for b in BLACKLIST):
                    domains.append(d)

        except Exception as e:
            log(f"Playwright 失败: {e}")
        finally:
            browser.close()

    # 去重保序
    seen = set()
    result = []
    for d in domains:
        d = d.lower().replace("www.", "").strip()
        if d and d not in seen:
            seen.add(d)
            result.append(d)
    return result


def update_gist(domains):
    """更新 Gist"""
    if not GH_TOKEN or not GIST_ID:
        log("GH_TOKEN 或 GIST_ID 未配置，跳过 Gist 更新")
        return False

    content = "\n".join(domains)
    payload = json.dumps({
        "files": {
            "3s.txt": {"content": content}
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            log(f"Gist 更新成功: HTTP {r.status}")
            return True
    except Exception as e:
        log(f"Gist 更新失败: {e}")
        return False


def main():
    log("=" * 50)
    log("开始抓取域名")
    log("=" * 50)

    domains = fetch_via_playwright()

    if not domains:
        log("Playwright 没抓到，用兜底列表")
        domains = list(FALLBACK)

    log(f"最终域名列表 ({len(domains)} 个): {domains}")
    update_gist(domains)


if __name__ == "__main__":
    main()
