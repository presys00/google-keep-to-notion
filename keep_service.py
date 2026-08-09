from datetime import datetime, timedelta, timezone
import gkeepapi


class KeepService:
    """Google Keep API (gkeepapi) との操作を集約するサービスクラス。

    gkeepapi の「メモリ上で高速に変更を行い、最後に 1 回だけ keep.sync() を呼ぶことで
    Google サーバーへの通信負荷・時間を最少化できる」バッチ特性を活用する設計となっています。
    """

    def __init__(self, email: str, master_token: str):
        self.email = email
        self.master_token = master_token
        self.keep = gkeepapi.Keep()

    def login(self) -> None:
        """gkeepapi マスタートークンによる認証"""
        self.keep.authenticate(self.email, self.master_token)

    def get_or_create_label(self, name: str) -> gkeepapi.node.Label:
        """ラベルの存在確認と自動生成を隠蔽するヘルパー"""
        label = self.keep.findLabel(name)
        if not label:
            label = self.keep.createLabel(name)
        return label

    def fetch_unprocessed_notes(self) -> list[gkeepapi.node.Note]:
        """「NotionSync処理済」ラベルの有無で未同期ノートをフィルタリングし、二重送信を防ぐ。"""
        processed_label = self.get_or_create_label("NotionSync処理済")
        notes = self.keep.all()
        return [
            n
            for n in notes
            if not n.trashed and processed_label not in n.labels.all()
        ]

    def feedback_note_info(
        self, note: gkeepapi.node.Note, summary: str, tags: list[str]
    ) -> None:
        """Notion同期完了後、Keep側のノートにもタイトル（無題時のみ）とAIカテゴリタグを書き戻す。
        ここでは通信を行わずメモリ上の変更にとどめることで速度を維持します。
        """
        # 既存タイトルを尊重し、空のときのみ AI 要約をタイトルに補完する
        if not note.title or not note.title.strip():
            note.title = summary

        for tag_name in tags:
            label = self.get_or_create_label(tag_name)
            note.labels.add(label)

        processed_label = self.get_or_create_label("NotionSync処理済")
        note.labels.add(processed_label)

    def auto_archive_old_notes(self, days: int = 5) -> int:
        """Keep 画面の散らかりを防ぐため、一定日数経過したノートを自動アーカイブする。
        「自動アーカイブ対象外」ラベルが明示的に付与されている場合は保護します。
        """
        no_archive_label = self.get_or_create_label("自動アーカイブ対象外")
        now_utc = datetime.now(timezone.utc)
        target_time = now_utc - timedelta(days=days)

        archived_count = 0
        active_notes = [
            n for n in self.keep.all() if not n.trashed and not n.archived
        ]

        for note in active_notes:
            last_updated = (
                note.timestamps.updated
                if note.timestamps.updated
                else note.timestamps.created
            )
            if last_updated and last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            if last_updated and last_updated < target_time:
                if no_archive_label in note.labels.all():
                    continue
                note.archived = True
                archived_count += 1

        return archived_count

    def sync(self) -> None:
        """メモリ上の全変更（タイトル・ラベル・処理済フラグ・アーカイブ）を 1 回の通信でサーバーへ一括反映する。"""
        self.keep.sync()
