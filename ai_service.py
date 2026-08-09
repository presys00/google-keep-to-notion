import json
import time
from google import genai
from google.genai import types
from google.genai.errors import APIError


class AIService:
    """Gemini API と連携し、メモおよびWebコンテンツからの「1行要約」の生成と
    「カテゴリタグの分類・ガバナンス管理」を担当するサービスクラス。

    既存のNotionタグをコンテキストとして動的注入することで表記揺れを防ぎつつ、
    未定義ジャンルが登場した際のみ新タグを創出させるルール設計を集約しています。
    """

    # パブリック公開用の一般的で汎用的なデフォルト初期タグ
    DEFAULT_TAG_CANDIDATES = [
        "技術・開発",
        "デザイン・素材",
        "AI・ITツール",
        "ニュース・トレンド",
        "ビジネス・キャリア",
        "アイデア・メモ",
        "生活・雑記",
    ]

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    @classmethod
    def fallback_keyword_tags(cls, text_content: str, existing_tags: list[str]) -> list[str]:
        """APIエラーや解析漏れが発生した場合でも、特定キーワードが含まれていれば
        適切な汎用カテゴリを補正するためのフォールバックロジック。
        """
        tags = set()
        text_lower = text_content.lower()

        if any(k in text_lower for k in ["python", "github", "unity", "プログラム", "開発", "コード", "shader", "api"]):
            tags.add("技術・開発")
        if any(k in text_lower for k in ["chatgpt", "claude", "gemini", "llm", "ai", "comfyui", "suno"]):
            tags.add("AI・ITツール")
        if any(k in text_lower for k in ["デザイン", "配色", "coolors", "素材", "ui", "イラスト"]):
            tags.add("デザイン・素材")
        if any(k in text_lower for k in ["ニュース", "トレンド", "記事", "発表"]):
            tags.add("ニュース・トレンド")
        if any(k in text_lower for k in ["ビジネス", "仕事", "マーケティング", "キャリア"]):
            tags.add("ビジネス・キャリア")

        for ext in existing_tags:
            if ext.lower() in text_lower:
                tags.add(ext)

        if not tags:
            tags.add("生活・雑記")

        return list(tags)[:3]

    def summarize_and_tag(
        self,
        note_text: str,
        web_title: str,
        web_body: str,
        existing_tags: list[str],
        note_title: str = "",
    ) -> dict[str, list[str] | str]:
        """Gemini 2.0 Flash を呼び出し、構造化JSONで要約とタグを取得する。"""
        combined_info = f"{note_title} {note_text} {web_title} {web_body}"
        combined_available_tags = list(set(self.DEFAULT_TAG_CANDIDATES + existing_tags))

        prompt = f"""
以下のメモ内容およびWebサイトの情報を厳密に分析し、一目で価値がわかる明瞭な1行要約と、最も適切なカテゴリタグを生成してJSONで出力してください。

【1行要約のルール】
- 50文字〜80文字程度の自然で具体的な日本語。
- 単なる「URLの掲載」や「〜のWebサイト」といった抽象的な要約は絶対禁止。どんな内容やツール、技術情報かを具体的に要約してください。

【タグ付け・ガバナンスルール (最重要・表記揺れ防止)】
1. 【表記揺れの防止】まずは以下の「利用可能な確定タグ一覧」の中に適合するものがあるか最優先で確認し、一致するものを選択してください。
   利用可能な確定タグ一覧: {json.dumps(combined_available_tags, ensure_ascii=False)}
2. 【新しいタグの動的創出】上記一覧のいずれにも適合しない全く新しいテーマ・分野（例: 料理・レシピ, マネー・投資, 医療・健康, アニメ・ゲーム 等）の場合に限り、適切な新しいタグ（日本語1〜2単語）を1つ新設して追加してください。
3. 【命名統一規則】新規タグを作成する場合は、同義語の表記乱造を避け、簡潔で洗練された名称にしてください。

【入力データ】
ノートタイトル: {note_title}
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
                response = self.client.models.generate_content(
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
                    tags_list = self.fallback_keyword_tags(combined_info, existing_tags)

                if not summary_str or summary_str.startswith("http"):
                    summary_str = f"{web_title or note_title or note_text[:40]}に関する解説情報"

                return {"summary": summary_str[:80], "tags": tags_list[:3]}
            except APIError as e:
                if e.code == 429:
                    time.sleep(15)
                else:
                    break
            except Exception:
                break

        fallback_tags = self.fallback_keyword_tags(combined_info, existing_tags)
        return {
            "summary": (web_title or note_title or note_text[:40])[:80],
            "tags": fallback_tags,
        }
