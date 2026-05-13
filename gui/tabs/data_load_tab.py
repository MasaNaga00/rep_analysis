"""
gui/tabs/data_load_tab.py - データ取得タブ

フェーズ3で実装する内容:
- データソース切り替え(SQL / CSV のラジオボタン)
- CSV モード:
  - ファイル選択ダイアログ
  - マッピングプリセット選択ドロップダウン
  - マッピング編集/新規作成ダイアログ(widgets/mapping_editor.py)
- SQL モード:
  - SQL クエリ入力(Text)
  - パラメータ入力
- 「読み込み」ボタン → Worker で loader 実行
- データプレビュー(pandastable)
- 言語分布・コメント長分布の表示
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class DataLoadTab(BaseTab):
    TITLE = "データ取得"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - SQL / CSV 切り替え\n"
                "  - マッピングプリセット選択\n"
                "  - マッピング新規作成/編集\n"
                "  - データプレビュー (pandastable)\n"
                "  - 言語・コメント長の分布表示"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
