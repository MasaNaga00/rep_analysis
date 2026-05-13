"""
dify_client.py - Dify APIクライアント

- 1回目（スキーマ生成）：同期で1回
- 2回目（タグ付け）：非同期並列でバッチ処理
- リトライ・JSON破損リカバリ付き
- CA証明書を指定したHTTPS接続（社内Dify対応）
"""
import asyncio
import json
import re
import ssl
import sys
from pathlib import Path
from typing import Optional
import aiohttp
import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type
)

import config


class DifyError(Exception):
    """Dify API関連の基底例外"""


class DifyJSONParseError(DifyError):
    """JSON解析失敗"""


class DifyCertificateError(DifyError):
    """CA証明書ファイルが見つからない・読み込めない"""


# ---------- CA証明書の解決 ----------

def _get_app_root() -> Path:
    """
    アプリのルートディレクトリを返す。
    
    - 通常実行: このファイル（dify_client.py）のあるディレクトリ
    - cx_Freeze 等で凍結された exe: 実行ファイルのあるディレクトリ
    """
    if getattr(sys, "frozen", False):
        # cx_Freeze / PyInstaller 等の凍結環境
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resolve_ca_cert_path(configured_path: Optional[str] = None) -> Path:
    """
    CA証明書ファイルのパスを解決して返す。
    
    探索順:
        1. 絶対パスならそのまま使用
        2. 相対パスなら ①アプリルート → ②カレントディレクトリ の順
    
    Args:
        configured_path: 設定された証明書パス（省略時は config.DIFY_CA_CERT_PATH）
    
    Returns:
        証明書ファイルの絶対パス
    
    Raises:
        DifyCertificateError: ファイルが見つからない
    """
    # 引数指定があれば優先、なければ config を使用
    # 空文字は「未設定」として扱う(GUI でクリアされたケース等)
    path_str = configured_path if configured_path is not None else config.DIFY_CA_CERT_PATH
    if not path_str:
        raise DifyCertificateError(
            "CA証明書パスが設定されていません。"
            "config.DIFY_CA_CERT_PATH または環境変数 DIFY_CA_CERT_PATH を確認してください。"
        )
    
    path = Path(path_str)
    
    if path.is_absolute():
        if not path.exists():
            raise DifyCertificateError(
                f"CA証明書ファイルが存在しません: {path}"
            )
        return path
    
    # 相対パスの場合は探索(重複は除去)
    seen = set()
    candidates = []
    for base in [_get_app_root(), Path.cwd()]:
        candidate = (base / path).resolve()
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    raise DifyCertificateError(
        f"CA証明書ファイル '{path_str}' が見つかりません。\n"
        f"以下を確認してください:\n"
        f"  探索した場所:\n"
        + "\n".join(f"    - {c}" for c in candidates)
        + f"\n  config.DIFY_CA_CERT_PATH = '{path_str}'"
    )


def _build_ssl_context(ca_cert_path: Optional[Path] = None) -> ssl.SSLContext:
    """
    aiohttp 用の SSLContext を構築する。
    
    Args:
        ca_cert_path: CA証明書パス（省略時は resolve_ca_cert_path を使用）
    """
    if ca_cert_path is None:
        ca_cert_path = resolve_ca_cert_path()
    
    try:
        ctx = ssl.create_default_context(cafile=str(ca_cert_path))
    except (ssl.SSLError, OSError) as e:
        raise DifyCertificateError(
            f"CA証明書ファイルの読み込みに失敗しました: {ca_cert_path}\n  エラー: {e}"
        )
    return ctx


# ---------- ユーティリティ ----------

def extract_json(text: str) -> dict | list:
    """
    LLM出力から JSON部分を抽出してパース。
    コードブロック記法・前後の説明文を除去。
    """
    text = text.strip()
    
    # コードブロック記法の除去
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    
    # 最初の { または [ から最後の } または ] まで抽出
    start_obj = text.find("{")
    start_arr = text.find("[")
    
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        start, end_char = start_arr, "]"
    elif start_obj != -1:
        start, end_char = start_obj, "}"
    else:
        raise DifyJSONParseError(f"JSONが見つかりません: {text[:200]}")
    
    end = text.rfind(end_char)
    if end == -1:
        raise DifyJSONParseError(f"JSON終端が見つかりません: {text[:200]}")
    
    json_str = text[start:end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise DifyJSONParseError(f"JSONパース失敗: {e}\n対象: {json_str[:500]}")


# ---------- 1回目：スキーマ生成（同期） ----------

@retry(
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, DifyJSONParseError)),
    reraise=True,
)
def generate_tag_schema(
    inquiry_text: str,
    max_detail_axes: int = 4,
    user_id: str = "repair-analysis",
) -> dict:
    """
    Dify 1回目ワークフローを呼び出し、タグスキーマを生成。
    
    Returns:
        {
            "axes": [...],
            "query_summary": "..."
        }
    """
    url = f"{config.DIFY_API_BASE}/workflows/run"
    headers = {
        "Authorization": f"Bearer {config.DIFY_API_KEY_SCHEMA}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {
            "inquiry_text": inquiry_text,
            "max_detail_axes": max_detail_axes,
        },
        "response_mode": "blocking",
        "user": user_id,
    }
    
    # CA証明書を指定してHTTPS接続
    ca_cert = resolve_ca_cert_path()
    
    resp = requests.post(
        url, headers=headers, json=payload,
        timeout=config.REQUEST_TIMEOUT,
        verify=str(ca_cert),
    )
    resp.raise_for_status()
    data = resp.json()
    
    # Difyワークフロー出力の取り出し
    # ワークフロー側で {"schema": {...}} を最終出力にしている前提
    outputs = data.get("data", {}).get("outputs", {})
    
    # パターンA: コードノードで {"success": true, "schema": {...}} を返す
    if "schema" in outputs:
        schema = outputs["schema"]
        if isinstance(schema, str):
            schema = extract_json(schema)
        return schema
    
    # パターンB: LLMノード直接出力（raw text）
    raw = outputs.get("text") or outputs.get("result") or next(iter(outputs.values()), "")
    if isinstance(raw, dict):
        return raw
    return extract_json(raw)


# ---------- 2回目：タグ付け（非同期バッチ） ----------

async def _call_dify_tagging(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    tag_schema: dict,
    inquiry_summary: str,
    batch: list[dict],
    batch_idx: int,
    user_id: str,
) -> dict:
    """1バッチ分のタグ付けを実行"""
    url = f"{config.DIFY_API_BASE}/workflows/run"
    headers = {
        "Authorization": f"Bearer {config.DIFY_API_KEY_TAGGING}",
        "Content-Type": "application/json",
    }
    
    # Difyに投入するrecords_json形式
    records_json = json.dumps([
        {"repair_id": r["repair_id"], "records": r["records"]}
        for r in batch
    ], ensure_ascii=False, indent=2)
    
    payload = {
        "inputs": {
            "tag_schema": json.dumps(tag_schema, ensure_ascii=False),
            "inquiry_summary": inquiry_summary,
            "records_json": records_json,
        },
        "response_mode": "blocking",
        "user": user_id,
    }
    
    async with semaphore:
        for attempt in range(config.MAX_RETRIES):
            try:
                async with session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                
                outputs = data.get("data", {}).get("outputs", {})
                raw = outputs.get("result") or outputs.get("text") or next(iter(outputs.values()), "")
                
                if isinstance(raw, list):
                    results = raw
                elif isinstance(raw, str):
                    results = extract_json(raw)
                else:
                    results = raw
                
                if not isinstance(results, list):
                    raise DifyJSONParseError(f"配列が期待されましたが {type(results)}")
                
                return {
                    "batch_idx": batch_idx,
                    "success": True,
                    "results": results,
                    "input_ids": [r["repair_id"] for r in batch],
                }
            
            except (aiohttp.ClientError, asyncio.TimeoutError, DifyJSONParseError) as e:
                if attempt == config.MAX_RETRIES - 1:
                    return {
                        "batch_idx": batch_idx,
                        "success": False,
                        "error": f"{type(e).__name__}: {e}",
                        "input_ids": [r["repair_id"] for r in batch],
                    }
                await asyncio.sleep(2 ** attempt)


async def tag_records_batch(
    tag_schema: dict,
    inquiry_summary: str,
    batches: list[list[dict]],
    user_id: str = "repair-analysis",
    progress_callback=None,
) -> list[dict]:
    """
    複数バッチを並列実行してタグ付け結果を返す。
    
    Args:
        tag_schema: 1回目で生成したスキーマ
        inquiry_summary: 問い合わせ要約
        batches: chunk_recordsで分割済みのバッチリスト
        progress_callback: 進捗通知用の関数 callback(done, total, last_result)
    
    Returns:
        各バッチの結果リスト
    """
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT)
    
    # CA証明書を指定したSSLコンテキストでaiohttpを初期化
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _call_dify_tagging(
                session, semaphore, tag_schema, inquiry_summary,
                batch, idx, user_id
            )
            for idx, batch in enumerate(batches)
        ]
        
        results = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            if progress_callback:
                progress_callback(len(results), len(tasks), result)
    
    # バッチ順にソート
    results.sort(key=lambda x: x["batch_idx"])
    return results


def run_tagging_sync(
    tag_schema: dict,
    inquiry_summary: str,
    batches: list[list[dict]],
    user_id: str = "repair-analysis",
    progress_callback=None,
) -> list[dict]:
    """
    Jupyter等から同期的に呼べるラッパー。
    既存のevent loopがあるかチェックして適切に処理。
    """
    try:
        loop = asyncio.get_running_loop()
        # Jupyterの既存ループ上で実行
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(
            tag_records_batch(tag_schema, inquiry_summary, batches, user_id, progress_callback)
        )
    except RuntimeError:
        # ループ未起動ならasyncio.run
        return asyncio.run(
            tag_records_batch(tag_schema, inquiry_summary, batches, user_id, progress_callback)
        )
