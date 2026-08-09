import os
import sys
from dotenv import load_dotenv
import gkeepapi

load_dotenv()

KEEP_EMAIL = os.getenv("KEEP_EMAIL")
KEEP_MASTER_TOKEN = os.getenv("KEEP_MASTER_TOKEN")

if not KEEP_EMAIL or not KEEP_MASTER_TOKEN:
    print("エラー: .env に KEEP_EMAIL または KEEP_MASTER_TOKEN が設定されていません。")
    sys.exit(1)

print("Google Keep にログイン中...")
keep = gkeepapi.Keep()
try:
    keep.authenticate(KEEP_EMAIL, KEEP_MASTER_TOKEN)
    print("ログイン成功。")
except Exception as e:
    print(f"ログイン失敗: {e}")
    sys.exit(1)

label_name = "自動アーカイブ対象外"
label = keep.findLabel(label_name)
if not label:
    print(f"ラベル 「{label_name}」 を作成中...")
    keep.createLabel(label_name)
    keep.sync()
    print(f"【成功】Google Keep に 「{label_name}」 ラベルを作成・同期しました！")
else:
    print(f"ラベル 「{label_name}」 は既に存在しています。")
