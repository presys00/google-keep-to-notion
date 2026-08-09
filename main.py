import sys
import time

from ai_service import AIService
from config import AppConfig
from keep_service import KeepService
from notion_service import NotionService
from web_scraper import WebScraper

# Windows コンソールでの UnicodeEncodeError (Shift-JIS/CP932 例外) を防ぐ安全設定
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class NotionSyncApp:
    """各モジュール（Config, Keep, Notion, AI, Scraper）を結合し、
    パイプライン全体の実行シーケンスを管理・制御するアプリケーションクラス。
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.notion_service = NotionService(
            api_key=config.notion_api_key,
            database_id=config.notion_database_id,
        )
        self.keep_service = KeepService(
            email=config.keep_email,
            master_token=config.keep_master_token,
        )
        self.ai_service = AIService(api_key=config.gemini_api_key)
        self.web_scraper = WebScraper()

    def run(self) -> None:
        """同期パイプラインの実行エントリーポイント"""
        print("=== NotionSync 起動 ===")

        # 1. 接続確認と既存タグコンテキストの学習
        print("Notion データベース接続確認中...")
        db_title = self.notion_service.verify_database_connection()
        existing_tags = self.notion_service.get_existing_tags()
        print(
            f"Notion データベース接続成功: 「{db_title}」 (既存登録タグ:"
            f" {len(existing_tags)}個 検出)"
        )

        # 2. Keep 認証と未処理ノートの特定
        print("Google Keep にログイン中...")
        self.keep_service.login()
        print("Google Keep ログイン成功。")

        unprocessed_notes = self.keep_service.fetch_unprocessed_notes()
        print(f"未同期の対象ノート件数: {len(unprocessed_notes)} 件")

        keep_stay_label = self.keep_service.get_or_create_label("Keep残し")

        # 3. ノートの順次同期・スクレイピング・AI解析・Notion登録・Keep書き戻し
        if unprocessed_notes:
            for i, note in enumerate(unprocessed_notes, 1):
                note_title_or_first_line = (
                    note.title if note.title else note.text.split("\n")[0]
                )
                if not note_title_or_first_line:
                    note_title_or_first_line = "無題のノート"

                print(
                    f"\n[{i}/{len(unprocessed_notes)}] ノート処理中:"
                    f" {note_title_or_first_line[:30]}"
                )

                if keep_stay_label and keep_stay_label in note.labels.all():
                    print(
                        "  -> 「Keep残し」ラベルを検出。Notionへの送信をスキップします。"
                    )
                else:
                    # Webコンテンツ情報の一括抽出 (安全なURLのみスクレイピング)
                    urls = self.web_scraper.extract_urls(note.text)
                    url = urls[0] if urls else None
                    web_title, web_body = "", ""
                    if url:
                        print(f"  -> URL検出: {url}")
                        _, web_title, web_body = (
                            self.web_scraper.fetch_page_content(url)
                        )

                    final_title = (
                        web_title if web_title else note_title_or_first_line
                    )

                    # 既存タグを考慮した AI 分析
                    print(
                        "  -> Gemini API (2.0-flash) で精密要約・タグ決定中"
                        " (ガバナンス適用)..."
                    )
                    ai_res = self.ai_service.summarize_and_tag(
                        note_text=note.text,
                        web_title=web_title,
                        web_body=web_body,
                        existing_tags=existing_tags,
                        note_title=note.title,
                    )
                    summary = ai_res["summary"]
                    tags = ai_res["tags"]

                    print(
                        f"  -> Notionへ保存中... (タグ: {tags}, 要約:"
                        f" {summary[:25]}...)"
                    )
                    try:
                        self.notion_service.create_page(
                            title=final_title,
                            summary=summary,
                            tags=tags,
                            url=url,
                            full_text=note.text,
                        )
                        print("  -> Notion保存成功！")

                        # 既存タグ一覧のリアルタイム更新
                        for t in tags:
                            if t not in existing_tags:
                                existing_tags.append(t)
                    except Exception as e:
                        print(f"  [Notion保存エラー]: {e}")
                        continue

                    # Keep への対となる逆フィードバック
                    self.keep_service.feedback_note_info(
                        note=note, summary=summary, tags=tags
                    )
                    print("  -> Keepフィードバック完了 (タイトル・タグ設定)")

                time.sleep(12)
        else:
            print("未同期のノートはありません。")

        # 4. 5日経過ノートのアーカイブ
        print("\n--- 自動アーカイブ処理チェック中 ---")
        archived_count = self.keep_service.auto_archive_old_notes(days=5)
        print(f"合計 {archived_count} 件のノートをアーカイブしました。")

        # 5. Keep メモリ上の全変更を一括送信
        print("\nGoogle Keepへ全変更（一括バッチ同期中...）")
        self.keep_service.sync()
        print("=== NotionSync 完了 ===")


def main():
    try:
        config = AppConfig.from_env()
        app = NotionSyncApp(config)
        app.run()
    except Exception as e:
        print(f"【エラーが発生しました】: {e}")


if __name__ == "__main__":
    main()
