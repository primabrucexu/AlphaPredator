"""
韭研公社登录凭据侦查脚本
========================
使用方式：
  1. 安装依赖：pip install playwright && playwright install chromium
  2. 运行脚本：python sniff_jygs_auth.py
  3. 在弹出的浏览器窗口中完成登录
  4. 登录成功后脚本自动打印捕获到的凭据信息

脚本会检查：
  - 所有登录相关 API 的响应体（JSON）
  - 登录后的 Cookie（含 HttpOnly 标记）
  - 登录后的 localStorage / sessionStorage
  - 业务 API 请求头中的认证字段
"""

import asyncio
import json
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Request, Response

JYGS_BASE = "https://www.jiuyangongshe.com"

# 登录成功后通常会跳转到的 URL 特征（或消失的 URL 特征）
LOGIN_URL_KEYWORDS = ["login", "signin", "auth", "user/login", "account"]

# 响应体中可能是 Token 的字段名
TOKEN_FIELD_NAMES = {
    "token", "accessToken", "access_token", "Authorization",
    "sessionId", "session_id", "authToken", "auth_token",
    "jwt", "bearerToken", "userToken", "user_token",
}

captured = {
    "login_responses": [],   # 登录接口的响应
    "auth_headers": [],      # 业务接口的请求头
    "cookies": [],           # 登录后的所有 Cookie
    "storage": {},           # localStorage / sessionStorage
}


def looks_like_token(value: str) -> bool:
    """判断一个字符串是否像 Token（足够长、非中文）"""
    if not isinstance(value, str):
        return False
    return len(value) > 20 and not any("\u4e00" <= c <= "\u9fff" for c in value)


def extract_tokens_from_json(obj, path=""):
    """递归扫描 JSON 对象，找出所有像 Token 的字段"""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else k
            if k.lower() in {f.lower() for f in TOKEN_FIELD_NAMES} and looks_like_token(v):
                results.append({"field": current_path, "value": v})
            results.extend(extract_tokens_from_json(v, current_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(extract_tokens_from_json(item, f"{path}[{i}]"))
    return results


async def on_response(response: Response):
    """拦截所有响应，重点关注登录和业务接口"""
    url = response.url
    if not url.startswith(JYGS_BASE):
        return

    path = urlparse(url).path

    # 只关注 JSON 响应
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return

    try:
        body = await response.json()
    except Exception:
        return

    # 是否是登录相关接口
    is_login_api = any(kw in path.lower() for kw in LOGIN_URL_KEYWORDS)

    tokens = extract_tokens_from_json(body)

    if is_login_api or tokens:
        entry = {
            "url": url,
            "status": response.status,
            "is_login_api": is_login_api,
            "tokens_found": tokens,
            "body_preview": json.dumps(body, ensure_ascii=False)[:500],
        }
        captured["login_responses"].append(entry)
        if tokens:
            print(f"\n🔑 [响应 Token] {path}")
            for t in tokens:
                print(f"   字段: {t['field']}")
                print(f"   值:   {t['value'][:80]}...")


async def on_request(request: Request):
    """拦截业务 API 请求，检查认证请求头"""
    url = request.url
    if not url.startswith(JYGS_BASE):
        return

    path = urlparse(url).path

    # 跳过登录接口本身
    if any(kw in path.lower() for kw in LOGIN_URL_KEYWORDS):
        return

    headers = dict(request.headers)
    auth_headers = {
        k: v for k, v in headers.items()
        if k.lower() in ("authorization", "token", "x-token", "x-auth-token",
                         "x-access-token", "auth-token", "accesstoken")
        or (k.lower() == "cookie" and looks_like_token(v))
    }

    if auth_headers and path not in [e["path"] for e in captured["auth_headers"]]:
        captured["auth_headers"].append({"path": path, "headers": auth_headers})
        print(f"\n🔐 [请求头认证] {path}")
        for k, v in auth_headers.items():
            print(f"   {k}: {v[:80]}...")


async def main():
    print("=" * 60)
    print("韭研公社登录凭据侦查脚本")
    print("=" * 60)
    print("1. 浏览器窗口即将打开")
    print("2. 请在浏览器中完成登录")
    print("3. 登录后随意点击几个页面（触发业务请求）")
    print("4. 回到此终端，按 Enter 键结束并查看结果")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=500,850", "--window-position=50,50"],
        )
        context = await browser.new_context(
            viewport={"width": 500, "height": 850},
            # 模拟移动端 UA，因为该站是 app.jiuyangongshe.com
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = await context.new_page()

        # 注册拦截器
        page.on("response", on_response)
        page.on("request", on_request)

        try:
            await page.goto(JYGS_BASE, wait_until="domcontentloaded")
        except Exception:
            # 忽略非 2xx 状态码错误，页面仍会加载
            pass

        # 等待用户手动操作
        input("\n>>> 完成登录后，随意点几个页面，然后回到这里按 Enter 键...\n")

        # ── 收集 Cookie ──────────────────────────────────────────
        cookies = await context.cookies()
        jygs_cookies = [c for c in cookies if "jiuyangongshe" in c.get("domain", "")]
        captured["cookies"] = jygs_cookies

        # ── 收集 localStorage / sessionStorage ───────────────────
        storage_data = await page.evaluate("""() => {
            const result = { localStorage: {}, sessionStorage: {} };
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                result.localStorage[k] = localStorage.getItem(k);
            }
            for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                result.sessionStorage[k] = sessionStorage.getItem(k);
            }
            return result;
        }""")
        captured["storage"] = storage_data

        await browser.close()

    # ── 打印完整报告 ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📋 侦查报告")
    print("=" * 60)

    # Cookie 报告
    print("\n【1. Cookie】")
    if captured["cookies"]:
        for c in captured["cookies"]:
            http_only = "⚠️ HttpOnly（JS无法读取）" if c.get("httpOnly") else "✅ 普通（JS可读）"
            print(f"  名称: {c['name']}")
            print(f"  值:   {str(c['value'])[:80]}")
            print(f"  类型: {http_only}")
            print(f"  过期: {c.get('expires', '会话级')}")
            print()
    else:
        print("  未发现 Cookie")

    # localStorage 报告
    print("\n【2. localStorage】")
    ls = captured["storage"].get("localStorage", {})
    if ls:
        for k, v in ls.items():
            flag = "🔑" if looks_like_token(str(v)) else "  "
            print(f"  {flag} {k}: {str(v)[:100]}")
    else:
        print("  localStorage 为空")

    # sessionStorage 报告
    print("\n【3. sessionStorage】")
    ss = captured["storage"].get("sessionStorage", {})
    if ss:
        for k, v in ss.items():
            flag = "🔑" if looks_like_token(str(v)) else "  "
            print(f"  {flag} {k}: {str(v)[:100]}")
    else:
        print("  sessionStorage 为空")

    # 登录接口响应报告
    print("\n【4. 登录/认证相关接口响应】")
    if captured["login_responses"]:
        for entry in captured["login_responses"]:
            print(f"  URL: {entry['url']}")
            print(f"  状态码: {entry['status']}")
            if entry["tokens_found"]:
                for t in entry["tokens_found"]:
                    print(f"  🔑 {t['field']}: {t['value'][:80]}")
            print(f"  响应预览: {entry['body_preview'][:200]}")
            print()
    else:
        print("  未捕获到登录接口响应")

    # 业务接口认证头报告
    print("\n【5. 业务接口的认证请求头】")
    if captured["auth_headers"]:
        shown = set()
        for entry in captured["auth_headers"]:
            for k, v in entry["headers"].items():
                if k not in shown:
                    print(f"  请求头名称: {k}")
                    print(f"  示例值:     {v[:80]}")
                    shown.add(k)
    else:
        print("  未发现认证请求头（可能认证信息在 Cookie 中）")

    # 保存原始数据
    output_path = "jygs_auth_sniff_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ 完整原始数据已保存到: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

