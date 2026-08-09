from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import httpx


class WebScraper:
    """ノート内に含まれる URL 先のコンテンツ情報を収集する処理を担当するクラス。

    転送先（リダイレクト）まで追跡して OGP メタ概要や本文テキストを取得します。
    ローカルネットワークやプライベートIPへの不要な外部アクセスを遮断するセキュリティガードを含みます。
    """

    def __init__(self, user_agent: str | None = None):
        self.headers = {
            "User-Agent": user_agent
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    @staticmethod
    def extract_urls(text: str) -> list[str]:
        return re.findall(r"https?://[^\s]+", text)

    @staticmethod
    def is_safe_public_url(url: str) -> bool:
        """ローカルIP、内部ネットワーク、プライベートIPへの不要なアクセスや情報漏洩を防止するセキュリティフィルター。"""
        if not url or not url.startswith(("http://", "https://")):
            return False

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False

            hostname_lower = hostname.lower()

            # ローカルホストおよびプライベートIPレンジの遮断
            if hostname_lower in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
                return False

            if (
                hostname_lower.startswith("192.168.")
                or hostname_lower.startswith("10.")
                or hostname_lower.startswith("172.16.")
                or hostname_lower.endswith(".local")
            ):
                return False

            return True
        except Exception:
            return False

    def fetch_page_content(self, url: str) -> tuple[str, str, str]:
        """安全なパブリックURLのみリダイレクト追跡し、タイトル・概要文・本文ノイズ除去テキストを取得する。"""
        if not self.is_safe_public_url(url):
            return url, "", ""

        try:
            with httpx.Client(
                follow_redirects=True, timeout=10.0, headers=self.headers
            ) as client:
                res = client.get(url)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")

                title = ""
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title.get("content").strip()
                elif soup.title and soup.title.string:
                    title = soup.title.string.strip()

                og_desc = ""
                meta_og_desc = soup.find("meta", property="og:description")
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_og_desc and meta_og_desc.get("content"):
                    og_desc = meta_og_desc.get("content").strip()
                elif meta_desc and meta_desc.get("content"):
                    og_desc = meta_desc.get("content").strip()

                for el in soup(
                    ["script", "style", "header", "footer", "nav", "noscript", "svg"]
                ):
                    el.decompose()

                body_text = soup.get_text(separator="\n", strip=True)
                combined_text = (
                    f"【Web概要】:\n{og_desc}\n\n【Web本文】:\n{body_text[:2500]}"
                )
                return url, title, combined_text
        except Exception:
            return url, "", ""

    def fetch_batch_pages(self, urls: list[str], max_workers: int = 10) -> dict[str, tuple[str, str]]:
        """複数URLを安全なパブリックURLのみフィルタリングした上で、マルチスレッドで並列スクレイピングする。"""
        safe_urls = [u for u in set(urls) if self.is_safe_public_url(u)]
        results = {}

        if not safe_urls:
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self.fetch_page_content, url): url
                for url in safe_urls
            }
            for future in as_completed(future_to_url):
                url, title, body = future.result()
                if url:
                    results[url] = (title, body)

        return results
