import os
import re
import sys

from dotenv import load_dotenv
import gkeepapi
from notion_client import Client

# Windows コンソールでの UnicodeEncodeError を防ぐ安全設定
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

KEEP_EMAIL = os.getenv("KEEP_EMAIL")
KEEP_MASTER_TOKEN = os.getenv("KEEP_MASTER_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s]+", text)


def main():
    print("=== Notion -> Google Keep 一括フィードバックツール ===")
    notion = Client(auth=NOTION_API_KEY)
    keep = gkeepapi.Keep()

    print("Google Keep にログイン中...")
    try:
        keep.authenticate(KEEP_EMAIL, KEEP_MASTER_TOKEN)
        print("ログイン成功。")
    except Exception as e:
        print(f"Keep ログイン失敗: {e}")
        sys.exit(1)

    print("Notion 全ページのデータを取得中...")
    has_more = True
    next_cursor = None
    notion_pages = []

    while has_more:
        res = notion.search(
            query="",
            filter={"property": "object", "value": "page"},
            start_cursor=next_cursor,
            page_size=100,
        )
        notion_pages.extend(res.get("results", []))
        has_more = res.get("has_more", False)
        next_cursor = res.get("next_cursor")

    print(f"Notion から {len(notion_pages)} 件のデータを取得しました。")

    notion_map = {}
    for page in notion_pages:
        props = page.get("properties", {})

        summary = ""
        if "1行要約" in props and props["1行要約"].get("rich_text"):
            rt = props["1行要約"]["rich_text"]
            if rt:
                summary = rt[0].get("plain_text", "").strip()

        tags = []
        if "タグ" in props and props["タグ"].get("multi_select"):
            tags = [ms["name"] for ms in props["タグ"]["multi_select"]]

        url = ""
        if "URL" in props and props["URL"].get("url"):
            url = props["URL"]["url"]

        full_text = ""
        if "ノート全文" in props and props["ノート全文"].get("rich_text"):
            rt = props["ノート全文"]["rich_text"]
            if rt:
                full_text = rt[0].get("plain_text", "").strip()

        data = {"summary": summary, "tags": tags}
        if url:
            notion_map[url] = data
        if full_text:
            notion_map[full_text[:50]] = data

    print("Google Keep ノートの照合 & メモリ上での変更中...")
    all_keep_notes = keep.all()
    updated_count = 0

    for note in all_keep_notes:
        if note.trashed:
            continue

        url = None
        found_urls = extract_urls(note.text)
        if found_urls:
            url = found_urls[0]

        matched_data = None
        if url and url in notion_map:
            matched_data = notion_map[url]
        elif note.text[:50] in notion_map:
            matched_data = notion_map[note.text[:50]]

        if matched_data:
            summary = matched_data["summary"]
            tags = matched_data["tags"]

            if summary and (not note.title or not note.title.strip()):
                note.title = summary

            for tag_name in tags:
                label = keep.findLabel(tag_name)
                if not label:
                    label = keep.createLabel(tag_name)
                note.labels.add(label)

            updated_count += 1

    print(f"照合完了: {updated_count} 件の Keep ノートにタイトルとタグを設定しました。")

    print("Google Keep へ一括バッチ同期中... (1回の通信で反映)")
    keep.sync()
    print("=== Google Keep 一括フィードバック完了！ ===")


if __name__ == "__main__":
    main()
