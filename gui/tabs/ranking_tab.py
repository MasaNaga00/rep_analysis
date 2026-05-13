"""
gui/tabs/ranking_tab.py - 絞り込みタブ

フェーズ3で実装する内容:
- 問い合わせタグ(query_tags)の指定 UI
  - 各軸ごとにドロップダウンで候補から選択
  - core 軸は必須、detail 軸は任意
- min_relevance スライダー(0.0〜1.0)
- top_n スピンボックス
- 「絞り込み実行」ボタン → scoring.rank_results()
- 結果テーブル(pandastable で表示)
- 上位レコードの根拠表示(クリックで詳細展開)
"""
import tkinter as tk
from tkinter import ttk

from gui.tabs.base import BaseTab


class RankingTab(BaseTab):
    TITLE = "絞り込み"
    
    def build_ui(self):
        msg = ttk.Label(
            self,
            text=(
                f"[{self.TITLE}]\n\n"
                "フェーズ3で実装:\n"
                "  - query_tags 指定(各軸ドロップダウン)\n"
                "  - min_relevance / top_n 設定\n"
                "  - 結果テーブル (pandastable)\n"
                "  - 上位結果の根拠表示"
            ),
            anchor="center",
            justify="left",
            font=("", 12),
        )
        msg.pack(expand=True, fill="both", padx=20, pady=20)
