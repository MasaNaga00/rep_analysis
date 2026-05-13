"""
gui/tabs/tagging_tab.py - タグ付け実行タブ

フェーズ3で実装する内容:
- 実行前情報表示(レコード数、バッチ数、想定時間)
- 「タグ付け開始」ボタン → Worker で dify_client.run_tagging_sync() 実行
- 進捗バー(現在/全バッチ)
- ログ表示(Text widget、失敗バッチも表示)
- 失敗バッチ一覧
- 「失敗バッチを再実行」ボタン(BATCH_SIZE を半分にして再試行)
- 完了後のサマリー(成功/失敗カウント)
- キャンセルボタン(Worker.cancel)
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class TaggingTab(BaseTab):
    TITLE = "タグ付け実行"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - タグ付け実行ボタン\n"
                "  - 進捗バー + ログ表示\n"
                "  - 失敗バッチ再実行\n"
                "  - 完了サマリー"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
