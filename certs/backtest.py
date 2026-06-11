"""
backtest.py
===========
過去のアラート相当事例(ラベル)に対して検知性能を測り、感度パラメータ
(R = 悪化倍率, h = しきい値) をチューニングするための検証ハーネス。

データは一切外部に出さない。御社環境でラベル付きデータを入力すれば、
こちらで中身を見ることなく性能指標を出せる。

ラベルの与え方
--------------
labels: DataFrame。1行 = 1異常事例。最低限の列:
  - 監視単位を特定するキー (事業コード, 開発コード, 部番[, 販社])
  - 基準月 "ラベル経過月": 「ここで確認すべきだった」と分かっている経過月
    (社内で把握している発覚時点・確認時点の経過月)。

検知遅れ(delay)の符号
----------------------
  delay = 初アラート経過月 - ラベル経過月
    delay < 0 : 人手の発覚より「早く」検知できた(早期検知として望ましい)
    delay = 0 : 同時
    delay > 0 : 人手より遅れて検知
  「検知できた」とみなす窓は detect_window で指定(ラベル前 early_margin か月 ～
   ラベル後 late_margin か月 の間にアラートがあれば検知成功とする)。

誤報(false alarm)
-----------------
  ラベルの無い監視単位(平常系列)でアラートが出たら誤報。
  単位時間あたりに正規化して「監視単位・年あたり誤報数」で評価する(低頻度向け)。
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from cusum_monitor import monitor_all, UNIT_KEYS_WITH_SHA, UNIT_KEYS_AGG_SHA


def _first_alarm_keizoku(unit_result: pd.DataFrame, col_keizoku="経過月"):
    a = unit_result[unit_result["アラート"]]
    if len(a) == 0:
        return None
    return int(a[col_keizoku].min())


def evaluate(
    df: pd.DataFrame,
    labels: pd.DataFrame,
    unit_keys: list[str],
    stable_start_m: int,
    baseline_len: int,
    monitor_end_m: int,
    R: float,
    h: float,
    early_margin: int = 24,
    late_margin: int = 6,
    col_keizoku: str = "経過月",
    label_keizoku_col: str = "ラベル経過月",
) -> dict:
    """単一の (R, h) で全単位を監視し、検知性能をまとめて返す。

    Returns(dict)
      power            : ラベル事例のうち検知できた割合
      n_labeled        : ラベル事例数
      n_detected       : 検知できた事例数
      median_delay     : 検知事例の delay の中央値(負ほど早期、月)
      mean_delay
      fa_per_unit_year : 平常単位での誤報数 / 監視単位・年
      n_clean_units    : 平常(ラベル無し)単位数
      detail           : 事例ごとの明細 DataFrame
    """
    results = monitor_all(
        df, unit_keys, stable_start_m, baseline_len, monitor_end_m, R, h
    )

    # 監視単位ごとに結果を引けるよう辞書化
    res_by_unit = {key: g for key, g in results.groupby(unit_keys, dropna=False)}

    # ラベルキー(存在する列だけ使う)
    label_join_keys = [k for k in unit_keys if k in labels.columns]

    detail_rows = []
    labeled_unit_set = set()
    for _, lab in labels.iterrows():
        key = tuple(lab[k] for k in label_join_keys)
        if len(label_join_keys) < len(unit_keys):
            # 販社合算監視でラベルが販社別の場合などは合算キーに丸める
            key = tuple(lab[k] for k in unit_keys if k in labels.columns)
        # 単一キーの groupby は tuple でなくスカラになるため整合させる
        lookup = key if len(key) > 1 else key[0]
        labeled_unit_set.add(lookup)

        g = res_by_unit.get(lookup)
        lab_m = int(lab[label_keizoku_col])
        if g is None:
            detail_rows.append({"key": lookup, "ラベル経過月": lab_m,
                                "初アラート経過月": None, "delay": None,
                                "検知": False})
            continue
        fa = _first_alarm_keizoku(g, col_keizoku)
        if fa is None:
            detail_rows.append({"key": lookup, "ラベル経過月": lab_m,
                                "初アラート経過月": None, "delay": None,
                                "検知": False})
            continue
        delay = fa - lab_m
        detected = (-early_margin) <= delay <= late_margin
        detail_rows.append({"key": lookup, "ラベル経過月": lab_m,
                            "初アラート経過月": fa, "delay": delay,
                            "検知": bool(detected)})

    detail = pd.DataFrame(detail_rows)
    n_labeled = len(detail)
    detected_mask = detail["検知"] if n_labeled else pd.Series(dtype=bool)
    n_detected = int(detected_mask.sum()) if n_labeled else 0
    power = n_detected / n_labeled if n_labeled else float("nan")
    delays = detail.loc[detail["検知"], "delay"].dropna() if n_labeled else pd.Series(dtype=float)
    median_delay = float(delays.median()) if len(delays) else float("nan")
    mean_delay = float(delays.mean()) if len(delays) else float("nan")

    # 誤報: ラベルの無い単位でアラートが立った回数を、監視月数で正規化
    n_clean_units = 0
    fa_count = 0
    monitored_months = 0
    for key, g in res_by_unit.items():
        if key in labeled_unit_set:
            continue
        n_clean_units += 1
        monitored_months += len(g)
        fa_count += int(g["アラート"].sum())
    fa_per_unit_year = (
        fa_count / (monitored_months / 12.0) if monitored_months > 0 else float("nan")
    )

    return {
        "R": R, "h": h,
        "power": power, "n_labeled": n_labeled, "n_detected": n_detected,
        "median_delay": median_delay, "mean_delay": mean_delay,
        "fa_per_unit_year": fa_per_unit_year, "n_clean_units": n_clean_units,
        "detail": detail,
    }


def grid_search(
    df: pd.DataFrame,
    labels: pd.DataFrame,
    unit_keys: list[str],
    stable_start_m: int,
    baseline_len: int,
    monitor_end_m: int,
    R_grid,
    h_grid,
    **eval_kwargs,
) -> pd.DataFrame:
    """(R, h) の格子で性能を計算し、サマリ表を返す。

    返り値の各行が1つの (R, h)。power が高く、median_delay が小さく(=早期)、
    fa_per_unit_year が許容内、の操作点を選ぶ。
    """
    rows = []
    for R in R_grid:
        for h in h_grid:
            r = evaluate(
                df, labels, unit_keys, stable_start_m, baseline_len,
                monitor_end_m, R, h, **eval_kwargs,
            )
            r.pop("detail")
            rows.append(r)
    out = pd.DataFrame(rows)
    return out.sort_values(["fa_per_unit_year", "median_delay"]).reset_index(drop=True)


def suggest_operating_point(
    grid_result: pd.DataFrame,
    max_fa_per_unit_year: float,
    min_power: float = 0.8,
) -> pd.DataFrame:
    """誤報予算と最低検知率の制約を満たす操作点を、早期性(delay)順に並べて返す。"""
    cand = grid_result[
        (grid_result["fa_per_unit_year"] <= max_fa_per_unit_year)
        & (grid_result["power"] >= min_power)
    ].copy()
    return cand.sort_values(["median_delay", "fa_per_unit_year"]).reset_index(drop=True)
