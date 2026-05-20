from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from services.file_service import build_timestamped_filename, suffix_lower


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1")
SUPPORTED_TABULAR_SUFFIXES = {".csv", ".xlsm", ".xlsx"}


def _is_summary_numeric(series: pd.Series) -> bool:
    return is_numeric_dtype(series) and not is_bool_dtype(series)


def get_numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(column) for column in df.columns if _is_summary_numeric(df[column])]


def get_table_profile(df: pd.DataFrame) -> dict[str, object]:
    numeric_columns = get_numeric_columns(df)
    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": [str(column) for column in df.columns],
        "numeric_columns": numeric_columns,
    }


def _read_csv_with_fallbacks(file_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        for read_kwargs in (
            {"encoding": encoding},
            {"encoding": encoding, "sep": None, "engine": "python"},
        ):
            try:
                return pd.read_csv(BytesIO(file_bytes), **read_kwargs)
            except Exception as exc:  # pragma: no cover - fallback path
                last_error = exc
    raise ValueError(f"CSV 文件读取失败: {last_error}")


def load_tabular_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    suffix = suffix_lower(filename)
    if suffix not in SUPPORTED_TABULAR_SUFFIXES:
        raise ValueError("数据分析模块仅支持 CSV、XLSX、XLSM 文件。")

    if suffix == ".csv":
        return _read_csv_with_fallbacks(file_bytes)

    return pd.read_excel(BytesIO(file_bytes), sheet_name=0, engine="openpyxl")


def _build_overview_sheet(df: pd.DataFrame, source_name: str, selected_columns: list[str]) -> pd.DataFrame:
    numeric_columns = get_numeric_columns(df)
    rows = [
        {"项目": "源文件名", "值": source_name},
        {"项目": "生成时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"项目": "行数", "值": int(df.shape[0])},
        {"项目": "列数", "值": int(df.shape[1])},
        {"项目": "数值字段数量", "值": len(numeric_columns)},
        {"项目": "已选择汇总字段数量", "值": len(selected_columns)},
    ]
    return pd.DataFrame(rows)


def _build_columns_sheet(df: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = set(get_numeric_columns(df))
    rows: list[dict[str, object]] = []
    for column in df.columns:
        series = df[column]
        rows.append(
            {
                "字段名": str(column),
                "数据类型": str(series.dtype),
                "是否数值字段": "是" if str(column) in numeric_columns else "否",
                "缺失值数量": int(series.isna().sum()),
                "缺失率": round(float(series.isna().mean()) if len(series) else 0.0, 6),
            }
        )
    return pd.DataFrame(rows)


def _build_summary_sheet(df: pd.DataFrame, selected_columns: list[str]) -> pd.DataFrame:
    valid_columns = [column for column in selected_columns if column in df.columns]
    if not valid_columns:
        return pd.DataFrame([{"说明": "未选择数值字段，未生成汇总统计。"}])

    summary = df[valid_columns].describe().transpose()
    summary = summary.reset_index().rename(columns={"index": "字段名"})
    return summary


def _build_missing_sheet(df: pd.DataFrame) -> pd.DataFrame:
    missing = pd.DataFrame(
        {
            "字段名": [str(column) for column in df.columns],
            "缺失值数量": [int(df[column].isna().sum()) for column in df.columns],
            "缺失率": [round(float(df[column].isna().mean()) if len(df[column]) else 0.0, 6) for column in df.columns],
        }
    )
    if not missing.empty:
        missing = missing.sort_values(by="缺失值数量", ascending=False)
    return missing


def build_analysis_report(df: pd.DataFrame, selected_columns: list[str], source_name: str) -> tuple[bytes, str]:
    buffer = BytesIO()
    preview_df = df.head(20).copy()
    overview_df = _build_overview_sheet(df, source_name, selected_columns)
    columns_df = _build_columns_sheet(df)
    summary_df = _build_summary_sheet(df, selected_columns)
    missing_df = _build_missing_sheet(df)

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        overview_df.to_excel(writer, sheet_name="概览", index=False)
        columns_df.to_excel(writer, sheet_name="字段清单", index=False)
        preview_df.to_excel(writer, sheet_name="预览前20行", index=False)
        summary_df.to_excel(writer, sheet_name="数值汇总", index=False)
        missing_df.to_excel(writer, sheet_name="缺失值统计", index=False)

    buffer.seek(0)
    return buffer.getvalue(), build_timestamped_filename(source_name, ".xlsx", prefix="analysis_report")
