"""
gui/tabs/export_tab.py - 出力タブ

フェーズ3で実装する内容:
- output_tag 入力欄(ファイル名サフィックス)
- 出力先ディレクトリの確認・変更
- 「保存実行」ボタン → scoring.save_results()
- 出力ファイルの一覧表示
- ファイル選択 → エクスプローラー/Finder で開く
- Tableau で開きやすい CSV のパスを強調表示
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class ExportTab(BaseTab):
    TITLE = "出力"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - output_tag 入力\n"
                "  - 出力先ディレクトリ\n"
                "  - 保存実行ボタン\n"
                "  - 出力ファイル一覧"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
