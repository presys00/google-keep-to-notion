from notion_client import Client
from notion_client.errors import APIResponseError


class NotionService:
    """Notion API との低レベル通信を集約し、データベース検証、既存タグの一覧取得、
    ページの新規作成・更新を提供するサービスクラス。
    """

    def __init__(self, api_key: str, database_id: str):
        self.notion = Client(auth=api_key)
        self.database_id = database_id

    def verify_database_connection(self) -> str:
        """データベース接続を事前に検証する。"""
        try:
            db_info = self.notion.databases.retrieve(database_id=self.database_id)
            db_title = "無題"
            if db_info.get("title") and len(db_info["title"]) > 0:
                db_title = db_info["title"][0].get("plain_text", "無題")
            return db_title
        except APIResponseError as e:
            if "is a page, not a database" in str(e):
                raise ValueError(
                    "指定された ID は Notion の親ページ ID です。データベース直下の ID を指定してください。"
                )
            raise e

    def get_existing_tags(self) -> list[str]:
        """Notion データベースのスキーマから、登録済みマルチセレクトタグの一覧を取得する。"""
        try:
            db_info = self.notion.databases.retrieve(database_id=self.database_id)
            props = db_info.get("properties", {})
            if "タグ" in props and props["タグ"].get("type") == "multi_select":
                options = props["タグ"].get("multi_select", {}).get("options", [])
                return [opt["name"] for opt in options if "name" in opt]
        except Exception:
            pass
        return []

    def fetch_all_pages(self) -> list[dict]:
        """全件検索 API を用いて全ページオブジェクトを取得する。"""
        has_more = True
        next_cursor = None
        pages = []

        while has_more:
            res = self.notion.search(
                query="",
                filter={"property": "object", "value": "page"},
                start_cursor=next_cursor,
                page_size=100,
            )
            pages.extend(res.get("results", []))
            has_more = res.get("has_more", False)
            next_cursor = res.get("next_cursor")

        return pages

    def create_page(
        self,
        title: str,
        summary: str,
        tags: list[str],
        url: str | None,
        full_text: str,
    ) -> None:
        """Notion データベースにプロパティと本文ブロックを構造化して登録する。
        タイトルが空文字の場合の API エラー (HTTP 400) を防ぐため、フォールバック値を適用します。
        """
        safe_title = (title.strip() if title else "") or "無題のノート"

        properties = {
            "タイトル": {
                "title": [{"text": {"content": self._truncate_string(safe_title, 100)}}]
            },
            "1行要約": {
                "rich_text": [
                    {"text": {"content": self._truncate_string(summary, 2000)}}
                ]
            },
            "タグ": {"multi_select": [{"name": tag} for tag in tags]},
            "ノート全文": {
                "rich_text": [
                    {"text": {"content": self._truncate_string(full_text, 2000)}}
                ]
            },
        }

        if url:
            properties["URL"] = {"url": url}

        children_blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "Google Keep ノート内容"}}]
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"text": {"content": self._truncate_string(full_text, 2000)}}
                    ]
                },
            },
        ]

        if url:
            children_blocks.append(
                {
                    "object": "block",
                    "type": "bookmark",
                    "bookmark": {"url": url},
                }
            )

        self.notion.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
            children=children_blocks,
        )

    def update_page_summary_and_tags(
        self, page_id: str, summary: str, tags: list[str]
    ) -> None:
        """既存ページの 1行要約 と タグ を再解析結果で上書き更新する。"""
        self.notion.pages.update(
            page_id=page_id,
            properties={
                "1行要約": {
                    "rich_text": [{"text": {"content": self._truncate_string(summary, 2000)}}]
                },
                "タグ": {
                    "multi_select": [{"name": tag} for tag in tags]
                },
            },
        )

    @staticmethod
    def _truncate_string(s: str, max_length: int = 2000) -> str:
        """Notion API の RichText 文字数制限 (2000文字) による HTTP 400 エラーを防止する安全用ガード。"""
        if len(s) > max_length:
            return s[: max_length - 3] + "..."
        return s
