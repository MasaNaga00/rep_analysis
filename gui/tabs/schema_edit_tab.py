"""
gui/tabs/schema_edit_tab.py - スキーマ編集タブ

フェーズ3で実装する内容:
- AppState.schema の軸一覧表示(Treeview)
- 軸の追加・削除・編集ダイアログ
- 軸内 candidates の追加・削除・編集
- core/detail tier の制約バリデーション(core は1個のみ等)
- query_summary の編集
- スキーマプレビュー(JSON 表示)
- 「初期化(再生成結果に戻す)」ボタン
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class SchemaEditTab(BaseTab):
    TITLE = "スキーマ編集"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - 軸の追加/削除/編集\n"
                "  - candidates 編集\n"
                "  - tier バリデーション\n"
                "  - JSON プレビュー"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
