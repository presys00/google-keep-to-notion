# NotionSync

Google Keep のメモを取得し、Gemini API で要約・タグ付けを行って Notion データベースへ同期するツールです。

---

## 機能概要

- **Web ページの深掘りスクレイピング (並列処理)**:
  ノートに含まれる URL や引用リンクを `httpx` (リダイレクト追跡) および `BeautifulSoup` で並列取得し、OGP タイトル・概要文・本文を取得します。
- **Gemini API による要約とカテゴリ分類**:
  メモの内容および Web ページのテキスト情報を分析し、1行要約（50〜80文字）と汎用カテゴリタグ（`技術・開発`, `デザイン・素材`, `AI・ITツール`, `ニュース・トレンド`, `ビジネス・キャリア` 等）を自動判定します。
- **Notion 既存タグのリアルタイム取得と表記の統一**:
  Notion データベース内に既に存在するタグ一覧を取得してプロンプトに含めることで、同義語によるタグの表記揺れを抑制します。既存カテゴリに該当しない場合のみ、新しいタグを生成します。
- **Google Keep へのタイトル・タグ書き戻しとバッチ同期**:
  タイトルが空のノートには生成した要約をタイトルとして設定し、カテゴリタグを Keep のラベルとして追加します。変更はメモリ上で適用し、最後に一括同期 (`keep.sync()`) を行います。
- **経過ノートの自動アーカイブ**:
  最終更新から5日以上経過したノートを自動でアーカイブします。`自動アーカイブ対象外` ラベルが付いたノートはそのまま維持します。
- **GitHub Actions による定期実行**:
  日本時間 3:00 および 15:00 (`cron: '0 6,18 * * *'`) の定時スケジュールでワークフローを実行できます。

---

## アーキテクチャ

```mermaid
flowchart TD
    subgraph Google Keep
        A[未処理ノートの抽出]
    end

    subgraph パイプライン
        B[並列 Web スクレイピング]
        C[Notion 既存タグの取得]
        D[Gemini API による解析]
    end

    subgraph 同期・保存
        E[Notion データベースへの保存]
        F[Google Keep へタイトル・タグを反映]
        G[5日経過ノートの自動アーカイブ]
    end

    A --> B
    B --> C
    C --> D
    D --> E
    D --> F
    F --> G
    G --> H[keep.sync による一括反映]
```

---

## プロジェクト構成

| ファイル | 役割 |
| :--- | :--- |
| **`main.py`** | アプリケーションのエントリーポイント (`NotionSyncApp`) |
| **`config.py`** | 環境変数および設定管理 (`AppConfig`) |
| **`keep_service.py`** | Google Keep の認証・ノート抽出・バッチ同期 (`KeepService`) |
| **`notion_service.py`** | Notion API 接続・既存タグ取得・ページ操作 (`NotionService`) |
| **`ai_service.py`** | Gemini API による要約・タグ分類 (`AIService`) |
| **`web_scraper.py`** | Web スクレイピング処理 (`WebScraper`) |
| **`get_token.py`** | Google Keep マスタートークン取得ツール |
| **`feedback_keep.py`** | Notion のデータから Keep ノートへ一括フィードバックするツール |
| **`fix_notion_ai.py`** | Notion 既存ページを一括で要約・タグ更新するツール |
| **`.github/workflows/notionsync.yml`** | GitHub Actions 定期実行ワークフロー設定 |
| **`.env.example`** | 環境変数の設定サンプル |

---

## セットアップ手順

### 1. リポジトリのクローンと仮想環境の作成

```powershell
# クローン
git clone https://github.com/your-username/google_keep_to_notion.git
cd google_keep_to_notion

# 仮想環境の作成と有効化 (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 依存ライブラリのインストール
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Google Keep マスタートークンの取得

```powershell
python get_token.py
```
実行後、起動するブラウザ画面で Google アカウントにログインすると、トークンが取得され `.env` ファイルへ保存されます。

### 3. 環境変数 (`.env`) の設定

`.env` に以下の項目を設定します。

```env
KEEP_EMAIL=your_email@gmail.com
KEEP_MASTER_TOKEN=aas_et/...
GEMINI_API_KEY=AIzaSy...
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=your_notion_database_id
```

### 4. 実行方法

```powershell
python main.py
```

---

## GitHub Actions の設定

1. GitHub にリポジトリを作成してコードを Push します。
2. リポジトリの **Settings > Secrets and variables > Actions** に以下の Secrets を登録します。
   - `KEEP_EMAIL`
   - `KEEP_MASTER_TOKEN`
   - `GEMINI_API_KEY`
   - `NOTION_API_KEY`
   - `NOTION_DATABASE_ID`
3. 日本時間の 3:00 および 15:00 に自動実行されます。

---

## セキュリティについての注意

- `.env` や `KEEP_MASTER_TOKEN` は秘密情報です。`.gitignore` によりリポジトリの追跡対象から除外されています。
- リポジトリを公開する場合は、必ず Secrets 経由で環境変数を設定してください。

---

## ライセンス

MIT License
