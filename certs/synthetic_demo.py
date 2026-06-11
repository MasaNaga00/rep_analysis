"""
synthetic_demo.py
=================
疑似データで検知の仕組み全体を動作確認するためのデモ兼セルフテスト。

御社の実データは見られないので、このスクリプトは
  (1) 仕組みが理論通り動くか(=既知の異常を本当に検知できるか)を社内・社外問わず確認でき、
  (2) 実データ投入時の入力フォーマットとコードの使い方の実例にもなる、
という二役を担う。

疑似データの作り方:
  - 多数の監視単位を生成。各単位の累積販売台数は「製造立ち上げ→継続」で増加。
    一部はオプションで末期に伸びが鈍る(実稼働台数の頭打ちを模す)。
  - 平常時は月次使用数 ~ Poisson(lambda0 * 累積販売台数)。
  - 一部の単位に、ある経過月(onset)から平常レートが徐々に上がるドリフトを注入。
    これらが「ラベル付き異常事例」になる(onset を正解の基準月とする)。
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import cusum_monitor as cm
import backtest as bt


def make_synthetic(
    n_normal_units: int = 200,
    n_event_units: int = 40,
    months: int = 96,
    lambda0_mean: float = 8e-5,     # 1台・1か月あたりの平常故障率(低頻度)
    drift_factor_range=(1.8, 3.5),  # onset 後にレートが何倍まで上がるか
    drift_ramp_months: int = 12,    # 倍化に向けて立ち上がる月数(緩やかなドリフト)
    fleet_plateau_prob: float = 0.4,
    seed: int = 0,
):
    rng = np.random.default_rng(seed)
    rows = []
    labels = []

    def fleet_curve(plateau: bool):
        # 累積販売台数: 立ち上げ後ほぼ線形に増加。plateau=True なら末期に頭打ち。
        base = np.linspace(2000, 60000, months)
        if plateau:
            # 後半の伸びを鈍らせる(実稼働の頭打ち相当)
            ramp = np.linspace(0, 1, months) ** 0.5
            base = 2000 + 58000 * ramp
        return base.round().astype(float)

    def emit_unit(dev_code, has_event):
        plateau = rng.random() < fleet_plateau_prob
        fleet = fleet_curve(plateau)
        lam0 = lambda0_mean * rng.uniform(0.5, 1.8)  # 単位ごとに平常レートばらつき
        rate = np.full(months, lam0)

        onset = None
        if has_event:
            onset = int(rng.integers(36, months - 12))  # 安定期内で発生
            target = lam0 * rng.uniform(*drift_factor_range)
            for i in range(onset, months):
                frac = min(1.0, (i - onset + 1) / drift_ramp_months)
                rate[i] = lam0 + (target - lam0) * frac

        expected = rate * fleet
        usage = rng.poisson(expected)

        for m in range(months):
            rows.append({
                "事業コード": "BIZ1",
                "開発コード": dev_code,
                "部番": "100-0001-001",
                "販社": "S_ALL",
                "年月": 202000 + m,  # ダミー(経過月で監視するので形式は不問)
                "経過月": m,
                "月次使用数": int(usage[m]),
                "累積販売台数": float(fleet[m]),
            })
        if has_event:
            labels.append({
                "事業コード": "BIZ1",
                "開発コード": dev_code,
                "部番": "100-0001-001",
                "ラベル経過月": onset,  # 正解の発生時点
            })

    uid = 0
    for _ in range(n_normal_units):
        emit_unit(f"DEV{uid:04d}", has_event=False); uid += 1
    for _ in range(n_event_units):
        emit_unit(f"DEV{uid:04d}", has_event=True); uid += 1

    return pd.DataFrame(rows), pd.DataFrame(labels)


def main():
    df, labels = make_synthetic(seed=1)
    print(f"疑似データ: {df['開発コード'].nunique()} 単位, "
          f"ラベル付き異常 {len(labels)} 件")

    unit_keys = cm.UNIT_KEYS_AGG_SHA  # 販社合算で監視(疑似データは単一販社)

    # 安定期 [36, 90] を監視、先頭12か月をベースラインに
    common = dict(stable_start_m=36, baseline_len=12, monitor_end_m=90)

    # --- 単一パラメータでの動作確認 ---
    r = bt.evaluate(df, labels, unit_keys, **common, R=2.0, h=10.0)
    print("\n=== 単一設定 (R=2.0, h=10) ===")
    print(f"検知率 power      : {r['power']:.2f}  ({r['n_detected']}/{r['n_labeled']})")
    print(f"検知遅れ 中央値    : {r['median_delay']:.1f} か月 (負=人手より早い)")
    print(f"誤報/単位・年      : {r['fa_per_unit_year']:.4f}  (平常 {r['n_clean_units']} 単位)")

    # --- グリッドサーチ ---
    grid = bt.grid_search(
        df, labels, unit_keys, **common,
        R_grid=[1.5, 2.0, 2.5, 3.0],
        h_grid=[5, 8, 12, 18, 25],
    )
    print("\n=== グリッドサーチ(誤報少→多 順) ===")
    cols = ["R", "h", "power", "median_delay", "fa_per_unit_year"]
    with pd.option_context("display.width", 120):
        print(grid[cols].to_string(index=False))

    # --- 誤報予算を満たす操作点の提案 ---
    # 予算を厳しくすると候補が消えることもある(=トレードオフの可視化)。
    for max_fa, min_pw in [(0.02, 0.7), (0.10, 0.5)]:
        op = bt.suggest_operating_point(grid, max_fa_per_unit_year=max_fa, min_power=min_pw)
        print(f"\n=== 誤報 <= {max_fa}/単位・年 かつ 検知率 >= {min_pw} を満たす操作点(早期順) ===")
        if len(op):
            print(op[cols].to_string(index=False))
        else:
            print("条件を満たす操作点なし(予算を緩めるか baseline/監視レンジを見直す)")

    grid.to_csv("grid_result_demo.csv", index=False)
    print("\nグリッド結果を grid_result_demo.csv に保存しました。")


if __name__ == "__main__":
    main()
