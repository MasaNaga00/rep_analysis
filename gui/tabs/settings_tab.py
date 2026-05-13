"""
gui/tabs/settings_tab.py - 設定タブ

フェーズ3で実装する内容:
- Dify API キー入力欄(schema/tagging)
- API ベース URL
- MS SQL Server 接続情報
- バッチサイズ・並列数・タイムアウト等のパラメータ
- 出力ディレクトリ選択
- 「保存」ボタン → settings_store に書き込み
- 「現在の設定を config モジュールに反映」
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class SettingsTab(BaseTab):
    TITLE = "設定"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - Dify API キー入力\n"
                "  - MS SQL Server 接続情報\n"
                "  - 処理パラメータ(バッチサイズ等)\n"
                "  - 出力ディレクトリ"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
