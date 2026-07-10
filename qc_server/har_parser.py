#!/usr/bin/env python3
"""
HAR 解析工具 — 从 Chrome 导出的 HAR 文件中提取 Loupe API 路径

用法:
    python har_parser.py /path/to/network.har

输出: loupe_apis_extracted.json（供 sync_service 使用）
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def parse_har(har_path: str) -> dict:
    """解析 HAR 文件，提取可能的 API 端点"""
    with open(har_path, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har.get("log", {}).get("entries", [])
    results = {
        "base_url": "https://qms.bytedance.com",
        "apis": {},
        "cookie": "",
        "headers": {},
    }

    # 用于匹配的关键词
    search_keywords = ["list", "search", "page", "query", "order"]
    detail_keywords = ["detail", "info", "report", "inspect"]

    candidates = []

    for entry in entries:
        request = entry.get("request", {})
        url = request.get("url", "")
        method = request.get("method", "")
        headers_list = request.get("headers", [])

        # 只关注 qms.bytedance.com 的 XHR 请求
        if "qms.bytedance.com" not in url and "bytedance.com" not in url:
            continue

        parsed = urlparse(url)
        path = parsed.path

        # 过滤静态资源
        if any(path.endswith(ext) for ext in [".js", ".css", ".png", ".jpg", ".woff", ".svg"]):
            continue

        candidates.append({
            "url": url,
            "path": path,
            "method": method,
            "headers": headers_list,
        })

        # 提取 Cookie
        if not results["cookie"]:
            for h in headers_list:
                if h.get("name", "").lower() == "cookie":
                    results["cookie"] = h.get("value", "")

        # 提取其他关键 headers
        for h in headers_list:
            name = h.get("name", "").lower()
            if name in ("authorization", "x-csrf-token", "x-requested-with"):
                results["headers"][name] = h.get("value", "")

    # 智能识别搜索接口和详情接口
    for c in candidates:
        path_lower = c["path"].lower()

        if any(kw in path_lower for kw in search_keywords):
            if "order_search" not in results["apis"]:
                results["apis"]["order_search"] = {
                    "method": c["method"],
                    "path": c["path"],
                }
                # 提取请求体样例
                entry = _find_entry(entries, c["url"])
                if entry and entry.get("request", {}).get("postData", {}).get("text"):
                    results["apis"]["order_search"]["body_example"] = (
                        entry["request"]["postData"]["text"]
                    )
                # 提取响应样例
                if entry and entry.get("response", {}).get("content", {}).get("text"):
                    text = entry["response"]["content"]["text"]
                    try:
                        results["apis"]["order_search"]["response_example"] = json.loads(text)
                    except:
                        results["apis"]["order_search"]["response_example"] = text[:500]

        if any(kw in path_lower for kw in detail_keywords) and "{" not in c["path"]:
            if "order_detail" not in results["apis"]:
                results["apis"]["order_detail"] = {
                    "method": c["method"],
                    "path": c["path"],
                }
                entry = _find_entry(entries, c["url"])
                if entry and entry.get("response", {}).get("content", {}).get("text"):
                    text = entry["response"]["content"]["text"]
                    try:
                        results["apis"]["order_detail"]["response_example"] = json.loads(text)
                    except:
                        results["apis"]["order_detail"]["response_example"] = text[:500]

    # 如果没识别到，列出所有候选让用户手动选
    if not results["apis"]:
        results["_all_candidates"] = [
            {"url": c["url"], "method": c["method"], "path": c["path"]}
            for c in candidates
        ]

    return results


def _find_entry(entries: list, url: str) -> dict:
    for e in entries:
        if e.get("request", {}).get("url", "") == url:
            return e
    return None


def main():
    if len(sys.argv) < 2:
        print("用法: python har_parser.py /path/to/network.har")
        sys.exit(1)

    har_path = sys.argv[1]
    if not Path(har_path).exists():
        print(f"文件不存在: {har_path}")
        sys.exit(1)

    print(f"解析 HAR 文件: {har_path}")
    results = parse_har(har_path)

    output_path = Path(__file__).parent / "loupe_apis_extracted.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ 提取完成 → {output_path}")
    print()

    if results["cookie"]:
        print(f"Cookie: {results['cookie'][:50]}...")
    else:
        print("⚠️  未提取到 Cookie，请手动填入 config_sync.json")

    apis = results.get("apis", {})
    if apis:
        print("\n识别到的 API:")
        for name, info in apis.items():
            print(f"  {name}: {info['method']} {info['path']}")

        if "order_search" in apis and "response_example" in apis["order_search"]:
            print("\n搜索接口响应样例（前 200 字符）:")
            print(f"  {str(apis['order_search']['response_example'])[:200]}")
    else:
        print("\n⚠️  未能自动识别 API，请查看 loupe_apis_extracted.json 中的 _all_candidates")
        print("   手动填写到 config_sync.json")


if __name__ == "__main__":
    main()
