import os
import secrets
import sys
import urllib.parse

import gpsoauth
from playwright.sync_api import sync_playwright


def main():
    print(
        "=== Google Keep マスタートークン全自動取得ツール (Playwright版) ==="
    )
    print(
        "自動でブラウザが開きます。画面上で普通に Google ログインを行ってください。"
    )
    print(
        "ログインが完了すると、本ツールが自動でトークンを抽出・検出します。\n"
    )

    email = input("Gmail アドレスを入力してください: ").strip()
    if not email:
        print("エラー: メールアドレスが入力されていません。")
        sys.exit(1)

    captured_token = None

    def handle_request(request):
        nonlocal captured_token
        url = request.url
        if "oauth_token=" in url:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if "oauth_token" in params:
                captured_token = params["oauth_token"][0]

    print("\nブラウザ画面を起動中... (しばらくお待ちください)")

    try:
        with sync_playwright() as p:
            # モバイル端末のユーザーエージェントでブラウザを起動
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
                    " (KHTML, like Gecko) Chrome/120.0.0.0 Mobile"
                    " Safari/537.36"
                ),
                viewport={"width": 450, "height": 700},
            )
            page = context.new_page()
            page.on("request", handle_request)

            page.goto("https://accounts.google.com/EmbeddedSetup")

            print("\n--------------------------------------------------")
            print(
                "★ 開いたブラウザ画面で Google ログインを完了させてください。"
            )
            print("--------------------------------------------------\n")

            # ユーザーのログイン完了とトークン生成を最大3分間自動待機
            for _ in range(180):
                page.wait_for_timeout(1000)

                if captured_token:
                    break

                # Cookie 内の oauth_token をチェック
                cookies = context.cookies()
                for cookie in cookies:
                    if cookie["name"] == "oauth_token":
                        captured_token = cookie["value"]
                        break

                if captured_token:
                    break

                # 画面URLパラメータにトークンが含まれているかチェック
                current_url = page.url
                if "oauth_token=" in current_url:
                    parsed = urllib.parse.urlparse(current_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "oauth_token" in params:
                        captured_token = params["oauth_token"][0]
                        break

            browser.close()
    except Exception as e:
        print(f"\n【ブラウザ起動エラー】: {e}")
        sys.exit(1)

    if not captured_token:
        print(
            "\n【エラー】トークンの自動検出タイムアウト、またはログインが未完了です。"
        )
        sys.exit(1)

    print("\n[成功] oauth_token の自動検出に成功しました！")
    print("Google 認証サーバーでマスタートークンに変換中...")

    android_id = secrets.token_hex(8)
    res = gpsoauth.exchange_token(email, captured_token, android_id)

    if "Token" in res:
        master_token = res["Token"]
        print("\n" + "=" * 50)
        print("【成功】マスタートークンを取得しました！")
        print("以下を .env や GitHub Secrets の KEEP_MASTER_TOKEN に設定してください:\n")
        print(master_token)
        print("=" * 50 + "\n")

        # .env ファイルの自動生成 / 保存アシスト
        env_path = ".env"
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"KEEP_EMAIL={email}\n")
                f.write(f"KEEP_MASTER_TOKEN={master_token}\n")
                f.write("GEMINI_API_KEY=\n")
                f.write("NOTION_API_KEY=\n")
                f.write("NOTION_DATABASE_ID=\n")
            print("👉 `.env` ファイルを自動作成し、メールアドレスとトークンを保存しました！")
    else:
        print("\n【認証エラー】Googleからの返答データ:")
        print(res)


if __name__ == "__main__":
    main()
