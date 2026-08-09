from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
import httpx
from notion_client import Client

# Windows PowerShell での UnicodeEncodeError (Shift-JIS/CP932 エラー) を防ぐ設定
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

TAG_CANDIDATES = [
    "技術・開発",
    "デザイン・素材",
    "AI・ITツール",
    "ニュース・トレンド",
    "ビジネス・キャリア",
    "アイデア・メモ",
    "生活・雑記",
]


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s]+", text)


def fetch_deep_web_content(url: str) -> tuple[str, str, str]:
    if not url:
        return "", "", ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        with httpx.Client(
            follow_redirects=True, timeout=10.0, headers=headers
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


def fallback_keyword_tags(text_content: str) -> list[str]:
    tags = set()
    text_lower = text_content.lower()

    if any(k in text_lower for k in ["python", "github", "unity", "プログラム", "開発", "コード", "shader"]):
        tags.add("技術・開発")
    if any(k in text_lower for k in ["chatgpt", "claude", "gemini", "llm", "ai", "comfyui"]):
        tags.add("AI・ITツール")
    if any(k in text_lower for k in ["デザイン", "配色", "coolors", "素材", "ui"]):
        tags.add("デザイン・素材")

    if not tags:
        tags.add("生活・雑記")

    return list(tags)[:3]


def summarize_and_tag(
    client: genai.Client, note_text: str, title: str, web_title: str, web_body: str
) -> dict:
    combined_info = f"{title} {note_text} {web_title} {web_body}"

    prompt = f"""
以下のメモ内容およびWebサイトの情報を厳密に分析し、一目で価値がわかる明瞭な1行要約と、最も適切なカテゴリタグを生成してJSONで出力してください。

【1行要約のルール】
- 50文字〜80文字程度の自然で具体的な日本語。
- 単なる「URLの掲載」や「〜のWebサイト」といった抽象的な要約は絶対禁止。

【タグ付けのルール】
- 以下のタグ候補リストの中から、該当するものを 1〜3個 必ず選んでください。
  タグ候補: {json.dumps(TAG_CANDIDATES, ensure_ascii=False)}

【入力データ】
ノートタイトル: {title}
ノート本文: {note_text}
Webタイトル: {web_title}
Web内容:
{web_body}

【出力形式 (JSON)】
{{
  "summary": "要約テキスト（50〜80文字）",
  "tags": ["技術・開発", "AI・ITツール"]
}}
"""
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash"]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            result = json.loads(response.text)
            summary_str = result.get("summary", "").strip()
            tags_list = result.get("tags", [])

            if not isinstance(tags_list, list) or len(tags_list) == 0 or tags_list == ["生活・雑記"]:
                tags_list = fallback_keyword_tags(combined_info)

            if not summary_str or summary_str.startswith("http"):
                summary_str = f"{web_title or title or note_text[:40]}に関する解説情報"

            return {"summary": summary_str[:80], "tags": tags_list[:3]}
        except APIError as e:
            if e.code == 429:
                time.sleep(12)
            else:
                continue
        except Exception:
            continue

    fallback_tags = fallback_keyword_tags(combined_info)
    return {
        "summary": (web_title or title or note_text[:40])[:80],
        "tags": fallback_tags,
    }


def main():
    print("=== NotionSync 高速再整理ツール ===")
    notion = Client(auth=NOTION_API_KEY)
    genai_client = genai.Client(api_key=GEMINI_API_KEY)

    print("Step 1: Notion 全件データの取得...")
    has_more = True
    next_cursor = None
    pages = []

    while has_more:
        res = notion.search(
            query="",
            filter={"property": "object", "value": "page"},
            start_cursor=next_cursor,
            page_size=100,
        )
        pages.extend(res.get("results", []))
        has_more = res.get("has_more", False)
        next_cursor = res.get("next_cursor")

    print(f"  -> 全 {len(pages)} 件の Notion ページを取得しました。")

    print("\nStep 2: 並列マルチスレッドによるWebスクレイピング実行中...")
    page_data_list = []
    urls_to_fetch = []

    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})

        title = "無題"
        for key in ["タイトル", "Title", "Name", "title", "name"]:
            if key in props and props[key].get("title"):
                title_objs = props[key]["title"]
                if title_objs:
                    title = title_objs[0].get("plain_text", "無題")
                    break

        full_text = ""
        for key in ["ノート全文", "FullText", "rich_text"]:
            if key in props and props[key].get("rich_text"):
                rt_objs = props[key]["rich_text"]
                if rt_objs:
                    full_text = rt_objs[0].get("plain_text", "")
                    break

        url = ""
        for key in ["URL", "url"]:
            if key in props and props[key].get("url"):
                url = props[key]["url"]
                break

        if not url:
            found_urls = extract_urls(full_text)
            if found_urls:
                url = found_urls[0]

        item = {
            "page_id": page_id,
            "title": title,
            "full_text": full_text,
            "url": url,
            "web_title": "",
            "web_body": "",
            "has_tags": "タグ" in props,
            "has_summary": "1行要約" in props,
        }
        page_data_list.append(item)
        if url:
            urls_to_fetch.append(url)

    unique_urls = list(set(urls_to_fetch))
    print(f"  -> 検出されたユニークURL {len(unique_urls)} 件を10スレッド並列で取得中...")

    web_results_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {
            executor.submit(fetch_deep_web_content, url): url
            for url in unique_urls
        }
        for future in as_completed(future_to_url):
            url, w_title, w_body = future.result()
            if url:
                web_results_map[url] = (w_title, w_body)

    print("  -> 並列Webスクレイピング完了！")

    print("\nStep 3: 高精度 AI 解析 & Notion 一括上書き更新中...")
    for i, item in enumerate(page_data_list, 1):
        url = item["url"]
        if url in web_results_map:
            item["web_title"], item["web_body"] = web_results_map[url]

        safe_title = item["title"][:30].encode("utf-8", errors="replace").decode("utf-8")
        print(f"[{i}/{len(page_data_list)}] 更新中: {safe_title}")

        ai_res = summarize_and_tag(
            genai_client,
            note_text=item["full_text"],
            title=item["title"],
            web_title=item["web_title"],
            web_body=item["web_body"],
        )
        new_summary = ai_res["summary"]
        new_tags = ai_res["tags"]

        print(f"  -> タグ: {new_tags}")
        print(f"  -> 要約: {new_summary}")

        update_props = {}
        if item["has_summary"]:
            update_props["1行要約"] = {
                "rich_text": [{"text": {"content": new_summary}}]
            }
        if item["has_tags"]:
            update_props["タグ"] = {
                "multi_select": [{"name": tag} for tag in new_tags]
            }

        if update_props:
            try:
                notion.pages.update(
                    page_id=item["page_id"], properties=update_props
                )
                print("  -> Notion更新成功！")
            except Exception as e:
                print(f"  [Notion更新エラー]: {e}")

        time.sleep(12)

    print("\n=== NotionSync 完了 ===")


if __name__ == "__main__":
    main()
