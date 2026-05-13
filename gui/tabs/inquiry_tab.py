"""
gui/tabs/inquiry_tab.py - 問い合わせタブ

フェーズ3で実装する内容:
- 問い合わせ文の複数行テキスト入力(Text widget)
- max_detail_axes スピンボックス
- 「スキーマ生成」ボタン
  → Worker で dify_client.generate_tag_schema() を実行
  → 完了時に AppState.schema に格納
  → スキーマ編集タブへ遷移を促す
- ログ表示エリア
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class InquiryTab(BaseTab):
    TITLE = "問い合わせ"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - 問い合わせ文入力\n"
                "  - スキーマ生成ボタン(Dify 1回目)\n"
                "  - 結果のログ表示"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
