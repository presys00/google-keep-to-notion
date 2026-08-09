import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    """アプリケーション全体の設定値と環境変数を集約・検証するクラス。

    起動時に各環境変数の存在をチェックし、URL形式で渡されたNotion Database IDから
    APIが求める32桁UUIDのみを正規抽出・クリーニングする役割を持ちます。
    """

    keep_email: str
    keep_master_token: str
    gemini_api_key: str
    notion_api_key: str
    notion_database_id: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        keep_email = os.getenv("KEEP_EMAIL", "").strip()
        keep_master_token = os.getenv("KEEP_MASTER_TOKEN", "").strip()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        notion_api_key = os.getenv("NOTION_API_KEY", "").strip()
        raw_db_id = os.getenv("NOTION_DATABASE_ID", "").strip()

        cleaned_db_id = cls._clean_database_id(raw_db_id)

        config = cls(
            keep_email=keep_email,
            keep_master_token=keep_master_token,
            gemini_api_key=gemini_api_key,
            notion_api_key=notion_api_key,
            notion_database_id=cleaned_db_id,
        )
        config.validate()
        return config

    @staticmethod
    def _clean_database_id(raw_id: str) -> str:
        """Notion ページの URL やハイフン付きUUIDが混在しても、
        Notion API が要求する標準ハイフン区切り UUID に変換するためのクリーニング処理。
        """
        if not raw_id:
            return ""
        match = re.search(r"([0-9a-f]{32})", raw_id.replace("-", ""), re.IGNORECASE)
        if match:
            hex_str = match.group(1).lower()
            return (
                f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"
            )
        return raw_id.strip()

    def validate(self) -> None:
        """必須パラメータの不足による実行途中のエラーを防ぐため、起動時に一括判定する"""
        missing = []
        if not self.keep_email:
            missing.append("KEEP_EMAIL")
        if not self.keep_master_token:
            missing.append("KEEP_MASTER_TOKEN")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not self.notion_api_key:
            missing.append("NOTION_API_KEY")
        if not self.notion_database_id:
            missing.append("NOTION_DATABASE_ID")

        if missing:
            raise ValueError(
                f"必須環境変数が設定されていません: {', '.join(missing)}"
            )
