#!/usr/bin/env python3
"""
ANP FPSO CSV Adapter — P0 专用适配器
=====================================

按《FPSO项目可用信息源使用手册》P0 要求实现：

来源信息:
  名称: ANP FPSO CSV
  URL:  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/
        arquivos-fase-de-desenvolvimento-e-producao/lpo/dados-abertos-plataformas-operacao.csv
  类型: CSV
  优先级: P0
  层级: 2 (官方验证)
  接入方式: 直接下载CSV + 字段映射 + 快照差异比较

功能:
  1. 下载 ANP 开放数据 CSV，解析为结构化数据。
  2. 以 "设施名称 + 运营商" 作为唯一键，保存当前快照。
  3. 与上一期快照（从 snapshot_registry 表读取）做差异比较。
  4. 输出 candidate_events，event_type = 'REGULATORY_DATA'。
  5. 保存原始 CSV 到 crawler/data/anp/ 目录，文件名包含日期。
  6. 记录文件哈希（SHA256）和下载时间。

合规:
  - 请求间隔遵守 robots.txt 和合理频率。
  - 保存原始文件和哈希，便于复核。
  - 严格区分来源发布日期和系统抓取时间。
  - 缺少证据时字段留空，不猜测。

Usage:
  python crawler/adapters/anp_fpso_csv.py                 # 完整运行: 下载 → 差异 → 写入
  python crawler/adapters/anp_fpso_csv.py --dry-run       # 仅下载并打印前5条
  python crawler/adapters/anp_fpso_csv.py --test          # 自测: 下载CSV输出前5条候选事件
  python crawler/adapters/anp_fpso_csv.py --no-diff       # 跳过差异比较，全部作为新事件
  python crawler/adapters/anp_fpso_csv.py --local-only    # 不写 Supabase，仅保存本地CSV
"""

import csv
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ---- Paths ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent  # crawler/
DATA_DIR = BASE_DIR / "data" / "anp"
ADAPTER_DIR = Path(__file__).resolve().parent  # crawler/adapters/

# ---- Config --------------------------------------------------------------

load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

# ANP CSV download URL.
# The /view page is a portal wrapper; the actual CSV is served via @@download/file.
# gov.br may return 403 without a proper User-Agent and may have SSL compatibility
# issues with older Python/OpenSSL versions.
ANP_CSV_URL = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
    "arquivos-fase-de-desenvolvimento-e-producao/lpo/dados-abertos-plataformas-operacao.csv"
    "/@@download/file"
)

# Fallback URL pattern for when ANP updates the CSV filename.
# Current file (as of 2026-07): instalacoes_maritimas_em_operacao_MM_YYYY.csv
ANP_CSV_FALLBACK_URL = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
    "arquivos-fase-de-desenvolvimento-e-producao/lpo/"
)

# Known download URLs to try in order
ANP_CSV_URLS = [ANP_CSV_URL]

# robots.txt for gov.br allows crawling with reasonable rate.
# We add a polite 2-second delay per request.
REQUEST_DELAY_SEC = 2.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; FPSOCrawler/1.0; +ANP-Open-Data-Adapter)"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anp-fpso-adapter")


# ============================================================================
# 1. CSV 字段映射规则
# ============================================================================
#
# ANP CSV 列名（葡萄牙语）→ 内部标准字段映射。
# 使用多种可能的列名（大小写不敏感匹配）以兼容 CSV 格式变化。
#
# 映射优先级: 精确匹配 → 去重音匹配 → 关键词包含匹配

COLUMN_MAP = {
    # 设施名称 (核心字段 — 唯一键组成部分)
    # ANP actual: "NOME DA INSTALAÇÃO" (installation name)
    "facility_name": [
        "nome da instalacao",
        "nome da instalação",
        "nome_da_instalacao",
        "nome_da_instalação",
        "nome da plataforma",
        "nome_da_plataforma",
        "plataforma",
        "instalacao",
        "instalação",
        "platform_name",
        "platform name",
        "nome",
        "name",
        "unidade",
        "unidade_estacionaria_de_producao",
    ],
    # 设施缩写 (ANP: "SIGLA DA INSTALAÇÃO")
    "facility_code": [
        "sigla da instalacao",
        "sigla da instalação",
        "sigla_da_instalacao",
        "sigla_da_instalação",
        "sigla",
        "abbreviation",
        "code",
        "codigo",
    ],
    # 运营商 (核心字段 — 唯一键组成部分)
    # ANP actual: "OPERADOR"
    "operator": [
        "operador",
        "operator",
        "operadora",
        "empresa_operadora",
        "concessionario",
        "concessionária",
        "concessionaria",
    ],
    # 盆地 (ANP: "BACIA")
    "basin": [
        "bacia",
        "basin",
        "bacia_sedimentar",
    ],
    # 油田/区块 (ANP: "CAMPOS")
    "field": [
        "campos",
        "campo",
        "field",
        "bloco",
        "block",
        "area",
        "área",
    ],
    # 平台类型 (ANP: "CLASSIFICAÇÃO" = e.g. "Floating Production Storage Offloading - FPSO")
    # 用于过滤 FPSO — 这是最重要的分类字段
    "platform_type": [
        "classificacao",
        "classificação",
        "classificacion",
        "classification",
        "tipo_de_plataforma",
        "tipo de plataforma",
        "tipo_plataforma",
        "tipo",
        "platform_type",
        "tipo_de_unidade",
        "tipo_da_unidade",
        "sistema_de_producao",
        "sistema_producao",
    ],
    # 投产年份 (ANP: "ANO DE INÍCIO DE OPERAÇÃO")
    "start_date": [
        "ano de inicio de operacao",
        "ano de início de operação",
        "ano_inicio_operacao",
        "inicio_de_operacao",
        "início de operação",
        "start_date",
        "data_inicio",
        "ano",
        "year",
    ],
    # 纬度 (ANP: "LATITUDE")
    "latitude": [
        "latitude",
        "lat",
    ],
    # 经度 (ANP: "LONGITUDE")
    "longitude": [
        "longitude",
        "lon",
        "long",
    ],
    # 水深 (ANP: "LÂMINA D'ÁGUA (m)")
    "water_depth_m": [
        "lamina d'agua",
        "lâmina d'água",
        "lamina dagua",
        "lâmina dágua",
        "water_depth",
        "water depth",
        "profundidade",
        "depth",
    ],
    # 外输系统 (ANP: "SISTEMA DE ESCOAMENTO")
    "offloading_system": [
        "sistema de escoamento",
        "sistema_escoamento",
        "offloading_system",
        "offloading",
        "escoamento",
    ],
    # 石油产能 (ANP: "CAPACIDADE DE PRODUÇÃO DE PETRÓLEO (bbl/d)")
    "oil_capacity_bbl_d": [
        "capacidade de producao de petroleo",
        "capacidade de produção de petróleo",
        "oil_capacity",
        "oil production capacity",
        "oil_capacity_bbl_d",
    ],
    # 天然气产能 (ANP: "CAPACIDADE DE PRODUÇÃO DE GÁS NATURAL (Mil m³/d)")
    "gas_capacity_m3_d": [
        "capacidade de producao de gas natural",
        "capacidade de produção de gás natural",
        "gas_capacity",
        "gas production capacity",
        "gas_capacity_m3_d",
    ],
}


def normalize_col_name(raw: str) -> str:
    """将原始列名标准化: 小写 + 去重音 + 去下划线 + 去多余空格。"""
    # Lowercase
    s = raw.strip().lower()
    # Remove accents (simple mapping for Portuguese)
    accents = {
        "á": "a", "à": "a", "ã": "a", "â": "a", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "õ": "o", "ô": "o", "ö": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
        "ñ": "n",
    }
    for accented, plain in accents.items():
        s = s.replace(accented, plain)
    # Replace underscores and repeated spaces with single space
    s = re.sub(r"[_]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def build_column_index(headers: list[str]) -> dict[str, int]:
    """
    根据 CSV 表头构建列索引映射。

    对每个已知字段，先用精确标准化匹配，再用模糊匹配。
    返回 {standard_field: csv_column_index} 字典。
    """
    norm_headers = [normalize_col_name(h) for h in headers]
    index = {}

    for std_field, aliases in COLUMN_MAP.items():
        # 标准化所有别名
        norm_aliases = [normalize_col_name(a) for a in aliases]

        # 第一轮: 精确匹配（标准化后完全相同）
        for i, nh in enumerate(norm_headers):
            if nh in norm_aliases:
                index[std_field] = i
                log.info("  Column map: %s → csv[%d] (%s)", std_field, i, headers[i])
                break

        # 第二轮: 包含匹配 (别名包含在 header 中 或 header 包含别名)
        # 对于 facility_name，优先匹配包含 "nome" 的列头
        if std_field not in index:
            candidates = []
            for i, nh in enumerate(norm_headers):
                for alias in norm_aliases:
                    if alias and (alias in nh or nh in alias):
                        candidates.append((i, nh, alias))
                        break  # 一个列只记录一次

            if candidates:
                # 偏好规则: facility_name 优先选带 "nome" 的列
                if std_field == "facility_name":
                    nome_candidates = [(i, nh, a) for i, nh, a in candidates if "nome" in nh]
                    if nome_candidates:
                        i, nh, alias = nome_candidates[0]
                    else:
                        i, nh, alias = candidates[0]
                # facility_code 优先选带 "sigla" 的列
                elif std_field == "facility_code":
                    sigla_candidates = [(i, nh, a) for i, nh, a in candidates if "sigla" in nh]
                    if sigla_candidates:
                        i, nh, alias = sigla_candidates[0]
                    else:
                        i, nh, alias = candidates[0]
                else:
                    i, nh, alias = candidates[0]

                index[std_field] = i
                log.info("  Column map (fuzzy): %s → csv[%d] (%s ≈ %s)",
                         std_field, i, headers[i], alias)

        if std_field not in index:
            log.debug("  Column map: %s → NOT FOUND", std_field)

    return index


# ============================================================================
# 2. CSV 下载与解析
# ============================================================================


def _build_govbr_session() -> requests.Session:
    """
    Build a requests Session tuned for Brazilian government servers.

    gov.br servers are known to:
    - Require modern TLS (1.2+) with specific cipher suites
    - Return 403 to requests with default Python User-Agent
    - Occasionally use TLSv1.3 that older OpenSSL builds don't handle

    We use a standard browser User-Agent and allow the session to
    negotiate the best available TLS version.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def _download_with_curl(url: str) -> bytes:
    """
    Fallback: download using system curl binary.

    gov.br servers have known SSL compatibility issues with Python's
    requests/urllib3 on certain OpenSSL versions. curl usually works.
    """
    import subprocess
    import tempfile

    log.info("Trying curl fallback for %s ...", url)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "curl", "-sS", "-L",
                "--max-time", "60",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept-Language: pt-BR,pt;q=0.9,en;q=0.5",
                "-o", tmp_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=65,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed with exit code {result.returncode}: {result.stderr}")

        raw = Path(tmp_path).read_bytes()
        if len(raw) == 0:
            raise RuntimeError("curl downloaded 0 bytes")
        log.info("curl downloaded %d bytes", len(raw))
        return raw
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def download_csv(url: str = None) -> tuple[bytes, str]:
    """
    下载 ANP CSV 文件。尝试多个已知 URL 模式。

    先用 Python requests 尝试，失败后回退到 curl。

    Returns:
        (raw_bytes, sha256_hex_digest)

    Raises:
        RuntimeError: 所有 URL 尝试均失败。
    """
    urls = [url] if url else ANP_CSV_URLS
    session = _build_govbr_session()

    last_error = None

    for attempt_url in urls:
        log.info("Downloading ANP CSV from %s ...", attempt_url)

        # Method 1: Python requests
        try:
            resp = session.get(attempt_url, timeout=60)
            resp.raise_for_status()
            raw = resp.content
            sha256 = hashlib.sha256(raw).hexdigest()
            log.info("Downloaded %d bytes (requests), SHA256=%s", len(raw), sha256)
            return raw, sha256
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            log.warning("Python requests SSL/connection error: %s", e)
            last_error = e
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') else '?'
            log.warning("HTTP %s for %s", status, attempt_url)
            last_error = e
            continue
        except requests.exceptions.RequestException as e:
            log.warning("Request failed: %s", e)
            last_error = e
            continue

        # Method 2: curl fallback (for gov.br SSL compatibility)
        try:
            raw = _download_with_curl(attempt_url)
            sha256 = hashlib.sha256(raw).hexdigest()
            log.info("Downloaded %d bytes (curl), SHA256=%s", len(raw), sha256)
            return raw, sha256
        except Exception as e:
            log.warning("curl fallback also failed: %s", e)
            last_error = e
            continue

    raise RuntimeError(
        f"Failed to download ANP CSV from all URLs. Last error: {last_error}. "
        f"gov.br may be blocking connections from outside Brazil. "
        f"Try downloading manually: curl -o anp.csv '{ANP_CSV_URL}'\n"
        f"Then place the CSV at {DATA_DIR}/YYYY-MM-DD_anp_fpso.csv"
    )


def save_raw_csv(raw: bytes, sha256: str, date_str: str = TODAY) -> Path:
    """保存原始 CSV 到 crawler/data/anp/YYYY-MM-DD_anp_fpso.csv。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{date_str}_anp_fpso.csv"
    filepath = DATA_DIR / filename
    filepath.write_bytes(raw)

    # 保存哈希文件
    hash_path = DATA_DIR / f"{date_str}_anp_fpso.csv.sha256"
    hash_path.write_text(f"{sha256}  {filename}\n")

    log.info("Saved raw CSV to %s", filepath)
    log.info("Saved hash to %s", hash_path)

    return filepath


def parse_csv(raw: bytes) -> tuple[list[dict], list[str]]:
    """
    解析 CSV 原始字节为结构化记录列表。

    自动检测编码（UTF-8 或 Latin-1），跳过空行。
    处理 UTF-8 BOM 标记。
    仅返回 platform_type 包含 'FPSO' 的记录。

    Returns:
        (records, csv_headers) — 每条记录是 {standard_field: value} 的字典。
    """
    # 编码检测: ANP 通常用 UTF-8-BOM 或 Latin-1
    for encoding in ["utf-8-sig", "utf-8", "latin-1", "iso-8859-1", "cp1252"]:
        try:
            text = raw.decode(encoding)
            log.info("CSV decoded as %s", encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Unable to decode ANP CSV with any known encoding")

    # Strip any remaining BOM from start of text
    if text and text[0] == "﻿":
        text = text[1:]

    # 用 csv.Sniffer 检测分隔符
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # 默认逗号

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)

    if len(rows) < 2:
        raise ValueError(f"CSV has only {len(rows)} rows; expected header + data")

    # Clean BOM from header row
    headers = [h.lstrip("﻿").strip() for h in rows[0]]
    col_index = build_column_index(headers)

    log.info("CSV headers (raw): %s", rows[0])
    log.info("Column index: %s", {k: headers[v] for k, v in col_index.items()})
    log.info("Total data rows: %d", len(rows) - 1)

    # 验证必需列
    required = ["facility_name", "operator"]
    missing = [r for r in required if r not in col_index]
    if missing:
        raise ValueError(
            f"Required columns not found in CSV: {missing}. "
            f"Available headers: {headers}"
        )

    records = []
    # ANP "CLASSIFICAÇÃO" values for FPSO types:
    # "Floating Production Storage Offloading - FPSO"
    fpso_keywords = [
        "fpso", "fps", "fso", "floating production storage",
        "fpso/m", "fpso/f",
    ]

    for row_num, row in enumerate(rows[1:], start=2):
        if not row or all(c.strip() == "" for c in row):
            continue  # 跳过空行

        record = {}
        for std_field, idx in col_index.items():
            if idx < len(row):
                val = row[idx].strip()
                # Normalize quotes around values (ANP sometimes wraps in quotes)
                val = val.strip('"').strip("'")
                record[std_field] = val
            else:
                record[std_field] = ""

        # 过滤: 仅保留 FPSO 类型平台
        ptype = record.get("platform_type", "").lower()
        is_fpso = any(kw in ptype for kw in fpso_keywords)

        if not is_fpso and ptype:
            # Also check facility name for FPSO prefix
            fname = record.get("facility_name", "").lower()
            facility_code = record.get("facility_code", "").lower()
            is_fpso = "fpso" in fname or "fpso" in facility_code

        if not is_fpso and ptype:
            # 非 FPSO，跳过 (e.g. SS = Semi-Submersible, FSO, fixed platform)
            log.debug("  Row %d: skipping non-FPSO type '%s' name='%s'",
                      row_num, record.get("platform_type", ""),
                      record.get("facility_name", ""))
            continue

        if is_fpso or not ptype:
            # 如果没有 platform_type 列，保留所有记录（用户可后续手动过滤）
            records.append(record)

    log.info("Parsed %d FPSO records from %d total data rows", len(records), len(rows) - 1)
    return records, headers


# ============================================================================
# 3. 唯一键 & 快照
# ============================================================================


def make_unique_key(record: dict) -> str:
    """
    构造唯一键: "设施名称 || 运营商"（大写标准化）。

    只取字母数字字符进行标准化，忽略大小写和标点差异。
    """
    name = record.get("facility_name", "").strip()
    operator = record.get("operator", "").strip()

    def _norm(s: str) -> str:
        """提取字母数字并大写。"""
        return re.sub(r"[^a-zA-Z0-9]", "", s).upper()

    return f"{_norm(name)}||{_norm(operator)}"


def build_snapshot(records: list[dict]) -> dict[str, dict]:
    """
    将记录列表转换为快照字典。

    Returns:
        {unique_key: record_dict}
    """
    snapshot = {}
    for r in records:
        key = make_unique_key(r)
        if key in snapshot:
            log.warning("Duplicate key in snapshot: %s (facility=%r, operator=%r)",
                        key, r.get("facility_name"), r.get("operator"))
            # 保留第一个（或可选择合并策略）
            continue
        snapshot[key] = r
    return snapshot


def save_snapshot_local(snapshot: dict[str, dict], date_str: str = TODAY) -> Path:
    """保存快照 JSON 到本地（总是保存，作为审计日志）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{date_str}_snapshot.json"

    # 转换为可序列化格式: key → record
    serializable = {}
    for key, record in snapshot.items():
        serializable[key] = {k: v for k, v in record.items()}

    filepath.write_text(
        json.dumps({
            "date": date_str,
            "fetched_at": NOW_ISO,
            "total_records": len(snapshot),
            "records": serializable,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved local snapshot to %s", filepath)
    return filepath


def load_previous_snapshot_local(date_str: str = None) -> Optional[dict[str, dict]]:
    """
    从本地文件加载上一期快照。
    查找 DATA_DIR 中最近的非今日快照 JSON。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snapshots = sorted(DATA_DIR.glob("*_snapshot.json"), reverse=True)

    if date_str:
        target = DATA_DIR / f"{date_str}_snapshot.json"
        if target.exists():
            data = json.loads(target.read_text(encoding="utf-8"))
            return data.get("records", {})

    for sp in snapshots:
        # 跳过今日快照
        if TODAY in sp.name:
            continue
        log.info("Loading previous snapshot from %s", sp)
        data = json.loads(sp.read_text(encoding="utf-8"))
        return data.get("records", {})

    log.info("No previous local snapshot found.")
    return None


# ============================================================================
# 4. 差异比较
# ============================================================================


def diff_snapshots(
    current: dict[str, dict],
    previous: Optional[dict[str, dict]],
) -> dict:
    """
    比较当前快照与上一期快照。

    Returns:
        {
            "new": [(key, record), ...],         # 新增设施
            "changed": [(key, old, new), ...],   # 状态/字段变更
            "removed": [(key, record), ...],      # 已移除设施
            "unchanged": [(key, record), ...],    # 无变化
        }
    """
    if previous is None:
        all_items = [(k, r) for k, r in current.items()]
        return {
            "new": all_items,
            "changed": [],
            "removed": [],
            "unchanged": [],
        }

    new = []
    changed = []
    removed = []
    unchanged = []

    current_keys = set(current.keys())
    previous_keys = set(previous.keys())

    # 新增
    for key in current_keys - previous_keys:
        new.append((key, current[key]))

    # 已移除
    for key in previous_keys - current_keys:
        removed.append((key, previous[key]))

    # 比较共同键
    for key in current_keys & previous_keys:
        cur = current[key]
        prev = previous[key]

        # 比较关键字段
        compare_fields = [
            "facility_name", "operator", "basin", "field",
            "platform_type", "start_date", "water_depth_m",
            "offloading_system", "oil_capacity_bbl_d", "gas_capacity_m3_d",
            "latitude", "longitude",
        ]
        diffs = []
        for f in compare_fields:
            cur_val = cur.get(f, "").strip()
            prev_val = prev.get(f, "").strip()
            if cur_val != prev_val:
                diffs.append((f, prev_val, cur_val))

        if diffs:
            changed.append((key, prev, cur, diffs))
        else:
            unchanged.append((key, cur))

    return {
        "new": new,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
    }


# ============================================================================
# 5. candidate_events 输出
# ============================================================================


def build_candidate_event(
    record: dict,
    event_type: str,
    change_details: Optional[str] = None,
    previous_record: Optional[dict] = None,
) -> dict:
    """
    将一条 ANP 记录转换为 candidate_events 表结构。

    candidate_events 列映射:
      project_name_raw ← facility_name
      country          ← "Brazil" (ANP = 巴西国家石油管理局)
      summary          ← 结构化摘要 (field/basin/phase/type)
      source_name      ← "ANP FPSO CSV"
      source_url       ← ANP CSV URL
      review_status    ← "pending"
      event_type       ← "REGULATORY_DATA"
      fetched_at       ← ISO 时间戳
      raw_json         ← 完整原始记录 (JSON string)
    """
    facility_name = record.get("facility_name", "").strip()
    operator = record.get("operator", "").strip()
    basin = record.get("basin", "").strip()
    field = record.get("field", "").strip()
    ptype = record.get("platform_type", "").strip()
    start_date = record.get("start_date", "").strip()
    water_depth = record.get("water_depth_m", "").strip()
    offloading = record.get("offloading_system", "").strip()
    oil_cap = record.get("oil_capacity_bbl_d", "").strip()
    gas_cap = record.get("gas_capacity_m3_d", "").strip()
    lat = record.get("latitude", "").strip()
    lon = record.get("longitude", "").strip()
    facility_code = record.get("facility_code", "").strip()

    # 构建结构化摘要
    summary_parts = []
    if operator:
        summary_parts.append(f"Operator: {operator}")
    if basin:
        summary_parts.append(f"Basin: {basin}")
    if field:
        summary_parts.append(f"Field: {field}")
    if ptype:
        summary_parts.append(f"Type: {ptype}")
    if start_date:
        summary_parts.append(f"Start: {start_date}")
    if water_depth:
        summary_parts.append(f"WaterDepth: {water_depth}m")
    if oil_cap:
        summary_parts.append(f"OilCap: {oil_cap} bbl/d")
    if gas_cap:
        summary_parts.append(f"GasCap: {gas_cap} Mm³/d")
    if offloading:
        summary_parts.append(f"Offloading: {offloading}")
    if lat and lon:
        summary_parts.append(f"Pos: {lat}, {lon}")

    summary = " | ".join(summary_parts) if summary_parts else ""

    # 如果有变更详情，追加到摘要
    if change_details:
        summary = f"[{event_type}] {change_details} | {summary}"

    return {
        "project_name_raw": facility_name,
        "country": "Brazil",
        "summary": summary[:500],
        "source_name": "ANP FPSO CSV",
        "source_url": ANP_CSV_URL,
        "review_status": "pending",
        "event_type": "REGULATORY_DATA",
        "fetched_at": NOW_ISO,
        # 审计字段: 保留原始 JSON
        "raw_json": json.dumps(record, ensure_ascii=False),
    }


def build_all_candidate_events(diff_result: dict) -> list[dict]:
    """
    将差异结果转换为 candidate_events 列表。

    仅输出变更（新增/变更/移除），不变的项目不产生事件。
    """
    events = []

    # 新增
    for key, record in diff_result["new"]:
        evt = build_candidate_event(record, event_type="NEW_FACILITY")
        evt["event_type"] = "REGULATORY_DATA"
        evt["change_type"] = "NEW_FACILITY"
        events.append(evt)

    # 变更
    for key, old, new, diffs in diff_result["changed"]:
        detail = "; ".join(f"{f}: {ov} -> {nv}" for f, ov, nv in diffs)
        evt = build_candidate_event(
            new,
            event_type="REGULATORY_DATA",
            change_details=f"FIELD_CHANGE: {detail}",
        )
        evt["change_type"] = "FIELD_CHANGE"
        evt["previous_raw_json"] = json.dumps(old, ensure_ascii=False)
        events.append(evt)

    # 移除
    for key, record in diff_result["removed"]:
        evt = build_candidate_event(record, event_type="REGULATORY_DATA")
        evt["event_type"] = "REGULATORY_DATA"
        evt["change_type"] = "REMOVED_FACILITY"
        evt["summary"] = f"[REMOVED from ANP dataset] {evt['summary']}"
        events.append(evt)

    return events


# ============================================================================
# 6. Supabase 写入
# ============================================================================


def get_supabase():
    """惰性初始化 Supabase 客户端。"""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env. "
            "Use --local-only to skip Supabase writes."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_candidate_events(events: list[dict], supabase=None) -> int:
    """写入 candidate_events 到 Supabase。"""
    if supabase is None:
        supabase = get_supabase()

    table = supabase.table("candidate_events")
    inserted = 0

    for evt in events:
        try:
            table.insert(evt).execute()
            inserted += 1
        except Exception:
            log.warning("Insert error for %s", evt.get("project_name_raw", "?"), exc_info=True)

    return inserted


def save_snapshot_to_registry(
    filepath: Path,
    sha256: str,
    record_count: int,
    supabase=None,
) -> bool:
    """
    将快照元数据写入 snapshot_registry 表。

    如果表不存在（首次运行），跳过并仅依赖本地快照。
    """
    if supabase is None:
        try:
            supabase = get_supabase()
        except RuntimeError:
            return False

    try:
        table = supabase.table("snapshot_registry")
        record = {
            "source_name": "ANP FPSO CSV",
            "source_url": ANP_CSV_URL,
            "snapshot_date": TODAY,
            "fetched_at": NOW_ISO,
            "file_path": str(filepath),
            "file_hash_sha256": sha256,
            "record_count": record_count,
            "source_type": "GOVERNMENT",
            "tier": 2,
            "priority": "P0",
            "country_focus": "Brazil",
            "access_method": "CSV",
        }
        table.insert(record).execute()
        log.info("Saved snapshot metadata to snapshot_registry")
        return True
    except Exception:
        log.warning("Could not write to snapshot_registry (table may not exist yet). "
                     "Local snapshot is saved and sufficient.")
        return False


def save_to_source_documents(file_path, file_hash_sha256, file_type,
                             file_size_bytes, original_url="",
                             download_url="", publication_date="",
                             supabase=None) -> bool:
    """Save downloaded file metadata to source_documents table.

    Per 《FPSO项目可用信息源使用手册》: records raw files in the
    source_documents layer for audit trail and deduplication.
    """
    if supabase is None:
        try:
            supabase = get_supabase()
        except RuntimeError:
            return False
    try:
        table = supabase.table("source_documents")
        record = {
            "file_name": Path(file_path).name,
            "file_path": str(file_path),
            "file_hash_sha256": file_hash_sha256,
            "file_type": file_type,
            "file_size_bytes": file_size_bytes,
            "publication_date": publication_date or TODAY,
            "fetched_at": NOW_ISO,
            "original_url": original_url or ANP_CSV_URL,
            "download_url": download_url or "",
        }
        table.insert(record).execute()
        log.info("Saved to source_documents: %s (%s, %d bytes)",
                 Path(file_path).name, file_type, file_size_bytes)
        return True
    except Exception:
        log.debug("Could not write to source_documents (table may not exist yet).")
        return False


# ============================================================================
# 7. 主流程
# ============================================================================


def run_adapter(
    dry_run: bool = False,
    no_diff: bool = False,
    local_only: bool = False,
    supabase=None,
) -> dict:
    """
    适配器主流程。

    Args:
        dry_run: 仅下载并打印前 N 条，不写入任何数据。
        no_diff: 跳过差异比较，所有记录作为 NEW_FACILITY。
        local_only: 不写入 Supabase，仅保存本地 CSV 和快照。
        supabase: Supabase 客户端（可选）。

    Returns:
        运行结果摘要字典。
    """
    log.info("=" * 60)
    log.info("ANP FPSO CSV Adapter — %s", TODAY)
    log.info("=" * 60)

    # 遵守 robots.txt: 延迟
    log.info("Waiting %.1fs (polite delay per robots.txt)...", REQUEST_DELAY_SEC)
    time.sleep(REQUEST_DELAY_SEC)

    # Step 1: 下载 CSV
    raw, sha256 = download_csv()
    filepath = save_raw_csv(raw, sha256)

    # Save to source_documents for audit trail
    if not local_only:
        save_to_source_documents(
            filepath, sha256, "CSV",
            len(raw),
            original_url=ANP_CSV_URL,
            supabase=supabase,
        )

    # Step 2: 解析 CSV
    records, headers = parse_csv(raw)

    if dry_run:
        log.info("--- DRY RUN: First 5 records ---")
        for i, r in enumerate(records[:5], 1):
            print(f"\n[{i}] {r.get('facility_name', '?')}")
            for k, v in r.items():
                if v:
                    print(f"    {k}: {v}")
        return {
            "mode": "dry_run",
            "total_records": len(records),
            "filepath": str(filepath),
            "sha256": sha256,
        }

    # Step 3: 构建当前快照
    current_snapshot = build_snapshot(records)
    save_snapshot_local(current_snapshot)

    # Step 4: 加载上一期快照并差异比较
    if no_diff:
        previous_snapshot = None
        log.info("--no-diff: all records will be treated as NEW_FACILITY")
    else:
        previous_snapshot = load_previous_snapshot_local()
        # 也尝试从 Supabase 加载（如果可用且 local_only=False）
        if not local_only and previous_snapshot is None:
            try:
                previous_snapshot = load_snapshot_from_supabase(supabase)
            except Exception:
                log.debug("Could not load snapshot from Supabase", exc_info=True)

    diff_result = diff_snapshots(current_snapshot, previous_snapshot)

    log.info("--- Diff Results ---")
    log.info("  New:        %d", len(diff_result["new"]))
    log.info("  Changed:    %d", len(diff_result["changed"]))
    log.info("  Removed:    %d", len(diff_result["removed"]))
    log.info("  Unchanged:  %d", len(diff_result["unchanged"]))

    # Step 5: 生成 candidate_events
    events = build_all_candidate_events(diff_result)
    log.info("Candidate events: %d", len(events))

    # Step 6: 写入 Supabase
    inserted = 0
    if not local_only and events:
        try:
            inserted = insert_candidate_events(events, supabase)
            log.info("Inserted %d candidate_events rows", inserted)
        except RuntimeError as e:
            log.warning("Skipping Supabase write: %s", e)

    # Step 7: 保存快照元数据到 Supabase
    if not local_only:
        try:
            save_snapshot_to_registry(filepath, sha256, len(records), supabase)
        except Exception:
            log.debug("snapshot_registry write skipped", exc_info=True)

    result = {
        "mode": "full",
        "total_records": len(records),
        "new": len(diff_result["new"]),
        "changed": len(diff_result["changed"]),
        "removed": len(diff_result["removed"]),
        "unchanged": len(diff_result["unchanged"]),
        "candidate_events": len(events),
        "inserted": inserted,
        "filepath": str(filepath),
        "sha256": sha256,
    }

    log.info("=" * 60)
    log.info("Run complete.")
    log.info("  Total FPSO records in CSV: %d", result["total_records"])
    log.info("  New: %d | Changed: %d | Removed: %d | Unchanged: %d",
             result["new"], result["changed"],
             result["removed"], result["unchanged"])
    log.info("  candidate_events written: %d/%d", result["inserted"], result["candidate_events"])
    log.info("  CSV saved: %s", result["filepath"])
    log.info("  SHA256: %s", result["sha256"])

    return result


def load_snapshot_from_supabase(supabase=None) -> Optional[dict[str, dict]]:
    """
    从 Supabase snapshot_registry 表加载上一期快照的原始数据。

    查找最新一条 ANP FPSO CSV 快照，下载其对应的 raw_json 字段。
    注意: 当前实现依赖本地快照 JSON 文件。
           snapshot_registry 主要存储元数据（hash, count, path），
           完整记录数据在本地 JSON 中。
    """
    # snapshot_registry 存储元数据而非完整记录。
    # 完整快照数据在 crawler/data/anp/*_snapshot.json 中。
    # 此函数作为 future-proof hook — 当 snapshot_registry 扩展了
    # raw_data 列后可从这里加载。
    return None


# ============================================================================
# 8. 自测逻辑
# ============================================================================


def run_test():
    """
    自测: 下载CSV，解析，输出前5条候选事件，验证字段完整性。

    不写入 Supabase，不保存快照。
    """
    log.info("=" * 60)
    log.info("SELF-TEST: ANP FPSO CSV Adapter")
    log.info("=" * 60)

    print("\n" + "─" * 60)
    print("Step 1: Download CSV")
    print("─" * 60)

    raw, sha256 = download_csv()
    print(f"  Downloaded: {len(raw):,} bytes")
    print(f"  SHA256: {sha256}")

    print("\n" + "─" * 60)
    print("Step 2: Parse CSV & Filter FPSO Records")
    print("─" * 60)

    records, headers = parse_csv(raw)
    print(f"  CSV columns ({len(headers)}): {headers}")
    print(f"  FPSO records found: {len(records)}")

    print("\n" + "─" * 60)
    print("Step 3: Build Candidate Events (first 5)")
    print("─" * 60)

    current_snapshot = build_snapshot(records)
    diff_result = diff_snapshots(current_snapshot, None)  # no previous = all new
    events = build_all_candidate_events(diff_result)

    required_fields = [
        "project_name_raw", "country", "summary", "source_name",
        "source_url", "review_status", "event_type", "fetched_at",
    ]

    for i, evt in enumerate(events[:5], 1):
        print(f"\n{'─' * 50}")
        print(f"Event #{i}")
        print(f"{'─' * 50}")

        for field in required_fields:
            val = evt.get(field, "MISSING")
            status = "✓" if val else "✗ EMPTY"
            print(f"  {status}  {field}: {val}")

        # 额外字段
        if evt.get("change_type"):
            print(f"  ✓  change_type: {evt['change_type']}")

        if evt.get("raw_json"):
            raw_preview = evt["raw_json"][:120]
            print(f"  ✓  raw_json: {raw_preview}...")

    # 字段完整性汇总
    print("\n" + "─" * 60)
    print("Step 4: Field Completeness Report")
    print("─" * 60)

    all_ok = True
    for i, evt in enumerate(events[:5], 1):
        missing = [f for f in required_fields if not evt.get(f)]
        if missing:
            print(f"  Event #{i}: MISSING {missing}")
            all_ok = False

    if all_ok:
        print("  All 5 events have complete required fields ✓")

    print(f"\n  Total candidate events (all new): {len(events)}")
    print(f"  Total FPSO records in CSV: {len(records)}")

    # 去重检查
    keys = [make_unique_key(r) for r in records]
    dupes = len(keys) - len(set(keys))
    if dupes:
        print(f"  ⚠ Duplicate keys found: {dupes}")
        # 列出重复项
        seen = {}
        for i, k in enumerate(keys):
            if k in seen:
                print(f"      Dup: {records[i].get('facility_name')} / {records[i].get('operator')}")
            else:
                seen[k] = i
    else:
        print(f"  All keys unique ✓")

    print("\n" + "─" * 60)
    print("Self-test complete.")
    print("─" * 60)

    return events


# ============================================================================
# 9. CLI
# ============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ANP FPSO CSV Adapter — P0专用适配器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler/adapters/anp_fpso_csv.py                # 完整运行
  python crawler/adapters/anp_fpso_csv.py --test         # 自测
  python crawler/adapters/anp_fpso_csv.py --dry-run      # 仅下载并打印前5条
  python crawler/adapters/anp_fpso_csv.py --no-diff      # 跳过差异比较
  python crawler/adapters/anp_fpso_csv.py --local-only   # 仅本地保存
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="自测: 下载CSV，输出前5条候选事件，验证字段完整性。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅下载并打印前5条记录，不写入任何数据。",
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="跳过差异比较，所有记录作为 NEW_FACILITY。",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="不写入 Supabase，仅保存本地 CSV 和快照。",
    )
    args = parser.parse_args()

    # 自测模式
    if args.test:
        try:
            run_test()
        except Exception as e:
            log.error("Self-test failed: %s", e, exc_info=True)
            sys.exit(1)
        return

    # 正常模式
    try:
        result = run_adapter(
            dry_run=args.dry_run,
            no_diff=args.no_diff,
            local_only=args.local_only,
        )
    except requests.exceptions.HTTPError as e:
        log.error("HTTP error downloading CSV: %s", e)
        sys.exit(1)
    except ValueError as e:
        log.error("CSV parsing error: %s", e)
        sys.exit(1)
    except Exception as e:
        log.error("Adapter failed: %s", e, exc_info=True)
        sys.exit(1)

    # 输出结果摘要
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
