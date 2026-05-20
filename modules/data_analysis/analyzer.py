from __future__ import annotations

import warnings
from datetime import datetime
from io import BytesIO

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from services.file_service import build_timestamped_filename, suffix_lower


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1")
SUPPORTED_TABULAR_SUFFIXES = {".csv", ".xls", ".xlsm", ".xlsx"}
PROFILE_SAMPLE_ROWS = 200_000
MAX_GROUP_ROWS = 5_000
MAX_TOP_VALUES_PER_DIMENSION = 20


def _make_unique_columns(columns) -> list[str]:
    seen: dict[str, int] = {}
    unique_columns: list[str] = []
    for index, column in enumerate(columns, start=1):
        name = str(column).strip()
        if not name or name.lower().startswith("unnamed:"):
            name = f"未命名字段_{index}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        unique_columns.append(name if count == 0 else f"{name}_{count + 1}")
    return unique_columns


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = _make_unique_columns(df.columns)
    return df


def _is_summary_numeric(series: pd.Series) -> bool:
    return is_numeric_dtype(series) and not is_bool_dtype(series)


def get_numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(column) for column in df.columns if _is_summary_numeric(df[column])]


def _safe_unique_count(series: pd.Series) -> int:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return int(series.astype("string").nunique(dropna=True))


def _sample_values(series: pd.Series, limit: int = 5) -> str:
    values = series.dropna().astype("string").head(limit).tolist()
    return "、".join(str(value)[:80] for value in values) if values else ""


def _numeric_success_rate(series: pd.Series) -> float:
    if _is_summary_numeric(series):
        return 1.0
    sample = series.dropna().head(1000)
    if sample.empty or is_bool_dtype(series):
        return 0.0
    parsed = pd.to_numeric(sample.astype("string").str.replace(",", "", regex=False), errors="coerce")
    return float(parsed.notna().mean())


def _date_success_rate(series: pd.Series) -> float:
    if is_datetime64_any_dtype(series):
        return 1.0
    if _is_summary_numeric(series) or is_bool_dtype(series):
        return 0.0
    sample = series.dropna().head(1000)
    if sample.empty:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(sample, errors="coerce")
    return float(parsed.notna().mean())


def _keyword_role_hint(column_name: str) -> str | None:
    name = column_name.lower()
    if any(keyword in name for keyword in ("日期", "时间", "年度", "年份", "月份", "date", "time", "year", "month")):
        return "时间"
    if any(keyword in name for keyword in ("id", "编号", "编码", "代码", "单号", "账号", "证件", "身份证")):
        return "ID/编号"
    return None


def _infer_column_role(column_name: str, series: pd.Series, row_count: int) -> tuple[str, str]:
    non_null_count = int(series.notna().sum())
    if non_null_count == 0:
        return "空字段", "整列为空"

    unique_count = _safe_unique_count(series)
    unique_ratio = unique_count / non_null_count if non_null_count else 0.0
    hint = _keyword_role_hint(column_name)
    numeric_rate = _numeric_success_rate(series)
    date_rate = _date_success_rate(series)

    if hint == "时间" and date_rate >= 0.5:
        return "时间", "字段名和内容都像时间字段"
    if hint == "时间":
        return "时间", "字段名像时间字段"
    if hint == "ID/编号":
        return "ID/编号", "唯一值占比较高，适合作为标识字段"
    if numeric_rate >= 0.8:
        if unique_count <= min(20, max(2, int(row_count * 0.05))):
            return "维度", "数值编码类字段，唯一值较少"
        return "指标", "可进行求和、均值、最大最小等数值汇总"
    if unique_ratio >= 0.95:
        return "ID/编号", "唯一值占比较高，适合作为标识字段"
    if date_rate >= 0.8:
        return "时间", "内容可解析为日期或时间"
    if unique_count <= min(200, max(20, int(row_count * 0.2))):
        return "维度", "分类值数量适中，适合分组分析"
    return "文本", "唯一值较多，更适合作为明细说明字段"


def get_column_profiles(df: pd.DataFrame) -> list[dict[str, object]]:
    row_count = int(df.shape[0])
    profile_df = df.head(PROFILE_SAMPLE_ROWS) if row_count > PROFILE_SAMPLE_ROWS else df
    profiles: list[dict[str, object]] = []

    for column in df.columns:
        column_name = str(column)
        series = profile_df[column]
        non_null_count = int(series.notna().sum())
        missing_count = int(row_count - int(df[column].notna().sum()))
        unique_count = _safe_unique_count(series)
        role, reason = _infer_column_role(column_name, series, row_count)
        profiles.append(
            {
                "字段名": column_name,
                "识别角色": role,
                "识别依据": reason,
                "数据类型": str(df[column].dtype),
                "非空数量": int(df[column].notna().sum()),
                "缺失值数量": missing_count,
                "缺失率": round(missing_count / row_count if row_count else 0.0, 6),
                "唯一值数量": unique_count,
                "样例值": _sample_values(series),
                "是否基于抽样": "是" if row_count > PROFILE_SAMPLE_ROWS else "否",
            }
        )

    return profiles


def get_smart_columns_from_profiles(profiles: list[dict[str, object]]) -> dict[str, list[str]]:
    return {
        "dimension_columns": [str(item["字段名"]) for item in profiles if item["识别角色"] in {"维度", "时间"}],
        "metric_columns": [str(item["字段名"]) for item in profiles if item["识别角色"] == "指标"],
        "date_columns": [str(item["字段名"]) for item in profiles if item["识别角色"] == "时间"],
        "id_columns": [str(item["字段名"]) for item in profiles if item["识别角色"] == "ID/编号"],
        "text_columns": [str(item["字段名"]) for item in profiles if item["识别角色"] == "文本"],
    }


def get_smart_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    return get_smart_columns_from_profiles(get_column_profiles(df))


def get_table_profile(df: pd.DataFrame, column_profiles: list[dict[str, object]] | None = None) -> dict[str, object]:
    numeric_columns = get_numeric_columns(df)
    smart_columns = get_smart_columns_from_profiles(column_profiles or get_column_profiles(df))
    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": [str(column) for column in df.columns],
        "numeric_columns": numeric_columns,
        **smart_columns,
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
        raise ValueError("数据分析模块仅支持 CSV、XLS、XLSX、XLSM 文件。")

    if suffix == ".csv":
        return _normalize_dataframe_columns(_read_csv_with_fallbacks(file_bytes))

    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    return _normalize_dataframe_columns(pd.read_excel(BytesIO(file_bytes), sheet_name=0, engine=engine))


def _build_overview_sheet(
    df: pd.DataFrame,
    source_name: str,
    selected_metrics: list[str],
    selected_dimensions: list[str],
    profiles: list[dict[str, object]],
) -> pd.DataFrame:
    role_counts = pd.Series([profile["识别角色"] for profile in profiles]).value_counts().to_dict()
    rows = [
        {"项目": "源文件名", "值": source_name},
        {"项目": "生成时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"项目": "行数", "值": int(df.shape[0])},
        {"项目": "列数", "值": int(df.shape[1])},
        {"项目": "自动识别维度字段数量", "值": int(role_counts.get("维度", 0))},
        {"项目": "自动识别时间字段数量", "值": int(role_counts.get("时间", 0))},
        {"项目": "自动识别指标字段数量", "值": int(role_counts.get("指标", 0))},
        {"项目": "自动识别ID字段数量", "值": int(role_counts.get("ID/编号", 0))},
        {"项目": "已选择维度字段数量", "值": len(selected_dimensions)},
        {"项目": "已选择指标字段数量", "值": len(selected_metrics)},
    ]
    return pd.DataFrame(rows)


def _build_columns_sheet(profiles: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(profiles)


def _coerce_numeric_frame(df: pd.DataFrame, selected_metrics: list[str]) -> pd.DataFrame:
    numeric_data: dict[str, pd.Series] = {}
    for column in selected_metrics:
        if column not in df.columns:
            continue
        series = df[column]
        if _is_summary_numeric(series):
            numeric_data[column] = series
        else:
            numeric_data[column] = pd.to_numeric(series.astype("string").str.replace(",", "", regex=False), errors="coerce")
    return pd.DataFrame(numeric_data)


def _build_summary_sheet(df: pd.DataFrame, selected_metrics: list[str]) -> pd.DataFrame:
    valid_columns = [column for column in selected_metrics if column in df.columns]
    if not valid_columns:
        return pd.DataFrame([{"说明": "未选择数值字段，未生成汇总统计。"}])

    metric_df = _coerce_numeric_frame(df, valid_columns)
    summary = metric_df.describe().transpose()
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


def _build_dimension_distribution_sheet(df: pd.DataFrame, selected_dimensions: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    row_count = len(df)
    for column in selected_dimensions:
        if column not in df.columns:
            continue
        counts = df[column].fillna("(空)").astype("string").value_counts(dropna=False).head(MAX_TOP_VALUES_PER_DIMENSION)
        for value, count in counts.items():
            rows.append(
                {
                    "维度字段": column,
                    "维度值": str(value)[:200],
                    "记录数": int(count),
                    "占比": round(int(count) / row_count if row_count else 0.0, 6),
                }
            )
    return pd.DataFrame(rows) if rows else pd.DataFrame([{"说明": "未选择维度字段，未生成维度分布。"}])


def _build_group_summary_sheet(
    df: pd.DataFrame,
    selected_dimensions: list[str],
    selected_metrics: list[str],
) -> pd.DataFrame:
    valid_dimensions = [column for column in selected_dimensions if column in df.columns]
    valid_metrics = [column for column in selected_metrics if column in df.columns]
    if not valid_dimensions or not valid_metrics:
        return pd.DataFrame([{"说明": "需要同时选择维度字段和指标字段，才会生成按维度汇总。"}])

    metric_df = _coerce_numeric_frame(df, valid_metrics)
    work_df = pd.concat([df[valid_dimensions], metric_df], axis=1)
    grouped = work_df.groupby(valid_dimensions, dropna=False)[valid_metrics].agg(["count", "sum", "mean", "min", "max"])
    grouped.columns = [f"{metric}_{agg}" for metric, agg in grouped.columns]
    grouped = grouped.reset_index()

    sort_column = f"{valid_metrics[0]}_sum"
    if sort_column in grouped.columns:
        grouped = grouped.sort_values(by=sort_column, ascending=False)
    return grouped.head(MAX_GROUP_ROWS)


def _build_auto_insights_sheet(
    df: pd.DataFrame,
    profiles: list[dict[str, object]],
    selected_dimensions: list[str],
    selected_metrics: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "类型": "数据规模",
            "发现": f"数据共 {df.shape[0]} 行、{df.shape[1]} 列。",
            "建议": "先关注缺失率高的字段、核心维度和核心指标。",
        }
    ]

    missing_profiles = sorted(profiles, key=lambda item: float(item["缺失率"]), reverse=True)
    for item in missing_profiles[:5]:
        if float(item["缺失率"]) > 0:
            rows.append(
                {
                    "类型": "数据质量",
                    "发现": f"{item['字段名']} 缺失率为 {float(item['缺失率']):.2%}。",
                    "建议": "分析前确认缺失值是否代表真实空值、未采集或业务上不适用。",
                }
            )

    for metric in selected_metrics[:5]:
        if metric not in df.columns:
            continue
        metric_series = _coerce_numeric_frame(df, [metric])[metric].dropna()
        if metric_series.empty:
            continue
        rows.append(
            {
                "类型": "指标概览",
                "发现": f"{metric} 总计 {metric_series.sum():,.2f}，平均 {metric_series.mean():,.2f}，最大 {metric_series.max():,.2f}。",
                "建议": "结合维度汇总表查看该指标主要由哪些类别贡献。",
            }
        )

    for dimension in selected_dimensions[:5]:
        if dimension not in df.columns:
            continue
        counts = df[dimension].fillna("(空)").astype("string").value_counts(dropna=False)
        if counts.empty:
            continue
        top_value = str(counts.index[0])
        top_count = int(counts.iloc[0])
        rows.append(
            {
                "类型": "维度分布",
                "发现": f"{dimension} 中占比最高的是“{top_value[:80]}”，共 {top_count} 条，占比 {top_count / len(df):.2%}。",
                "建议": "若头部类别占比过高，后续分析应单独观察该类别是否影响整体结论。",
            }
        )

    if len(rows) == 1:
        rows.append({"类型": "说明", "发现": "未识别到足够字段生成自动洞察。", "建议": "请检查字段名、字段类型或选择更多维度和指标。"})

    return pd.DataFrame(rows)


def build_analysis_report(
    df: pd.DataFrame,
    selected_columns: list[str],
    source_name: str,
    selected_dimensions: list[str] | None = None,
    column_profiles: list[dict[str, object]] | None = None,
) -> tuple[bytes, str]:
    selected_metrics = selected_columns
    selected_dimensions = selected_dimensions or []
    buffer = BytesIO()
    preview_df = df.head(20).copy()
    profiles = column_profiles or get_column_profiles(df)
    overview_df = _build_overview_sheet(df, source_name, selected_metrics, selected_dimensions, profiles)
    columns_df = _build_columns_sheet(profiles)
    summary_df = _build_summary_sheet(df, selected_metrics)
    missing_df = _build_missing_sheet(df)
    dimension_distribution_df = _build_dimension_distribution_sheet(df, selected_dimensions)
    group_summary_df = _build_group_summary_sheet(df, selected_dimensions, selected_metrics)
    auto_insights_df = _build_auto_insights_sheet(df, profiles, selected_dimensions, selected_metrics)

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        overview_df.to_excel(writer, sheet_name="概览", index=False)
        auto_insights_df.to_excel(writer, sheet_name="自动洞察", index=False)
        columns_df.to_excel(writer, sheet_name="字段智能识别", index=False)
        preview_df.to_excel(writer, sheet_name="预览前20行", index=False)
        summary_df.to_excel(writer, sheet_name="数值汇总", index=False)
        dimension_distribution_df.to_excel(writer, sheet_name="维度分布", index=False)
        group_summary_df.to_excel(writer, sheet_name="维度指标汇总", index=False)
        missing_df.to_excel(writer, sheet_name="缺失值统计", index=False)

    buffer.seek(0)
    return buffer.getvalue(), build_timestamped_filename(source_name, ".xlsx", prefix="analysis_report")
