"""
cusum_monitor.py
================
部品出庫の異常検知（安定期ドリフトの早期検知）コアモジュール。

設計の要点（詳細は設計ドキュメント・検証手順書を参照）:
  - 監視指標は「1台あたり月次故障ペース」。ただし生レートを正規分布扱いせず、
    月次使用数(離散カウント)を時変平均のポアソン過程として監視する。
  - 平常レート lambda0 は「安定期初期」で推定し固定する(ドリフト吸収を防ぐ)。
  - 期待故障数 = lambda0 * 累積販売台数 は保有台数の増加を自動で吸収するので、
    アラートはレートの上昇分にのみ反応する。
  - 累積販売台数が実稼働台数の近似として成立する経過月レンジに監視を限定する
    (退役が進む末期は分母が過大になり、本物の上昇をマスクするため)。

このモジュールは外部にデータを送らない。すべてローカルで完結する。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# 監視単位を一意に決めるキー。販社合算で監視するときは販社をキーから外す。
UNIT_KEYS_WITH_SHA = ["事業コード", "開発コード", "部番", "販社"]
UNIT_KEYS_AGG_SHA = ["事業コード", "開発コード", "部番"]


def estimate_lambda0(usage: np.ndarray, fleet: np.ndarray) -> float:
    """安定期初期の窓から平常レート lambda0(1台・1か月あたり故障率)を推定する。

    lambda0 = (窓内の月次使用数合計) / (窓内の累積販売台数合計)
    台数で重みづけした平均レートに相当する。
    """
    total_fleet = float(np.sum(fleet))
    if total_fleet <= 0:
        return 0.0
    return float(np.sum(usage)) / total_fleet


def poisson_cusum(
    usage: np.ndarray,
    fleet: np.ndarray,
    lambda0: float,
    R: float,
    h: float,
    reset_after_alarm: bool = True,
):
    """時変平均ポアソン上側CUSUM。

    Parameters
    ----------
    usage  : 各月の月次使用数(カウント)
    fleet  : 各月の累積販売台数(保有台数近似)。期待値の分母。
    lambda0: 平常レート(estimate_lambda0 で推定し固定したもの)
    R      : 検知したい悪化倍率 lambda1/lambda0 ( > 1 )。例: 2.0 は「レート倍化を狙う」
    h      : 判定しきい値(感度)。小さいほど早く鳴るが誤報増。
    reset_after_alarm: アラート後に統計量を0へ戻すか(再検知を許す)。

    Returns
    -------
    S      : CUSUM統計量の時系列
    alarm  : 各月のアラート真偽(S >= h)
    k      : 各月の参照値(時変)
    """
    usage = np.asarray(usage, dtype=float)
    fleet = np.asarray(fleet, dtype=float)
    n = len(usage)
    S = np.zeros(n)
    alarm = np.zeros(n, dtype=bool)
    k = np.zeros(n)

    if lambda0 <= 0 or R <= 1.0:
        # 平常レートが0、または悪化倍率が不正なら監視不能(全て非アラート)。
        return S, alarm, k

    lambda1 = R * lambda0
    log_ratio = np.log(R)
    # 時変参照値 k_t = (lambda1 - lambda0) * fleet_t / ln(lambda1/lambda0)
    k = (lambda1 - lambda0) * fleet / log_ratio

    s_prev = 0.0
    for t in range(n):
        s = max(0.0, s_prev + usage[t] - k[t])
        S[t] = s
        if s >= h:
            alarm[t] = True
            s_prev = 0.0 if reset_after_alarm else s
        else:
            s_prev = s
    return S, alarm, k


def monitor_unit(
    df_unit: pd.DataFrame,
    stable_start_m: int,
    baseline_len: int,
    monitor_end_m: int,
    R: float,
    h: float,
    col_keizoku: str = "経過月",
    col_usage: str = "月次使用数",
    col_fleet: str = "累積販売台数",
) -> pd.DataFrame:
    """1監視単位の時系列に対して、ベースライン推定 → CUSUM監視を行う。

    監視レンジは経過月 [stable_start_m, monitor_end_m]。
    ベースライン窓は経過月 [stable_start_m, stable_start_m + baseline_len)。
    monitor_end_m は退役で分母が過大になる前の上限(妥当性ウィンドウの末尾)。

    返り値は監視レンジの各月に対する結果テーブル。
    """
    d = df_unit.sort_values(col_keizoku).reset_index(drop=True)

    base_mask = (d[col_keizoku] >= stable_start_m) & (
        d[col_keizoku] < stable_start_m + baseline_len
    )
    mon_mask = (d[col_keizoku] >= stable_start_m) & (d[col_keizoku] <= monitor_end_m)

    base = d[base_mask]
    lambda0 = estimate_lambda0(
        base[col_usage].to_numpy(), base[col_fleet].to_numpy()
    )

    mon = d[mon_mask].copy()
    if len(mon) == 0:
        return mon

    S, alarm, k = poisson_cusum(
        mon[col_usage].to_numpy(), mon[col_fleet].to_numpy(), lambda0, R, h
    )
    mon["lambda0"] = lambda0
    mon["期待故障数"] = lambda0 * mon[col_fleet].to_numpy()
    mon["参照値k"] = k
    mon["CUSUM"] = S
    mon["しきい値h"] = h
    mon["アラート"] = alarm
    return mon


def monitor_all(
    df: pd.DataFrame,
    unit_keys: list[str],
    stable_start_m: int,
    baseline_len: int,
    monitor_end_m: int,
    R: float,
    h: float,
    **cols,
) -> pd.DataFrame:
    """全監視単位に monitor_unit を適用して結果を縦に結合する。

    unit_keys は UNIT_KEYS_WITH_SHA(販社別) か UNIT_KEYS_AGG_SHA(販社合算)。
    販社合算の場合は、呼び出し前に df を unit_keys + [年月, 経過月] で集約しておくこと
    (使用数・販売台数を合計する。aggregate_over_sha を参照)。
    """
    out = []
    for _, g in df.groupby(unit_keys, dropna=False):
        res = monitor_unit(
            g, stable_start_m, baseline_len, monitor_end_m, R, h, **cols
        )
        if len(res):
            out.append(res)
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True)


def aggregate_over_sha(
    df: pd.DataFrame,
    col_usage: str = "月次使用数",
    col_fleet: str = "累積販売台数",
) -> pd.DataFrame:
    """販社を合算した監視単位(機種×部番)を作る。

    使用数と累積販売台数を販社横断で合計する。経過月・年月は機種側で共通の想定。
    """
    keys = UNIT_KEYS_AGG_SHA + ["年月", "経過月"]
    agg = (
        df.groupby(keys, dropna=False)[[col_usage, col_fleet]]
        .sum()
        .reset_index()
    )
    return agg
