from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from modules.data_analysis import (
    build_analysis_report,
    get_numeric_columns,
    get_table_profile,
    load_tabular_dataframe,
)
from modules.file_converter import convert_file, get_conversion_label_for_file
from modules.image_processor import process_image
from services.file_service import file_signature, uploaded_file_bytes
from services.log_service import get_logger


ROOT_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT_DIR / "config" / "settings.json"
logger = get_logger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "app_name": "AI Office Automation Web",
    "app_title": "AI Office Automation Web",
    "max_preview_rows": 20,
    "default_image_width": 1024,
    "default_image_height": 768,
    "default_image_quality": 85,
    "max_upload_size_mb": 50,
}

MIME_MAP = {
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def load_settings() -> dict[str, Any]:
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("读取 settings.json 失败: %s", exc)
    return settings


SETTINGS = load_settings()


def apply_page_style() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 30%),
                radial-gradient(circle at top right, rgba(245, 158, 11, 0.10), transparent 32%),
                linear-gradient(180deg, #f8fafc 0%, #eff6f4 100%);
            color: #0f172a;
        }
        .block-container {
            max-width: 1180px;
            padding-top: 1.4rem;
            padding-bottom: 2rem;
        }
        .hero {
            border: 1px solid rgba(15, 118, 110, 0.15);
            border-radius: 24px;
            padding: 1.2rem 1.4rem;
            margin-bottom: 1rem;
            background: rgba(255, 255, 255, 0.72);
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
            backdrop-filter: blur(12px);
        }
        .hero h1 {
            margin: 0 0 0.35rem 0;
            font-size: 2rem;
            line-height: 1.15;
        }
        .hero p {
            margin: 0;
            color: #475569;
            font-size: 1rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
            background: rgba(255, 255, 255, 0.55);
            padding: 0.4rem;
            border-radius: 999px;
            border: 1px solid rgba(15, 118, 110, 0.12);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            padding: 0.45rem 0.9rem;
            background: transparent;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #0f766e, #0f9f8f);
            color: white;
        }
        .stButton > button {
            border-radius: 999px;
            border: 0;
            box-shadow: 0 8px 20px rgba(15, 118, 110, 0.18);
        }
        .stDownloadButton > button {
            border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero">
            <h1>{SETTINGS["app_title"]}</h1>
            <p>一个可直接部署到互联网的 Streamlit MVP，支持数据分析、文件格式转写和图片处理，所有处理结果都可以直接下载。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def reset_module_state(prefix: str, extra_keys: tuple[str, ...] = ()) -> None:
    keys_to_clear = {
        f"{prefix}_signature",
        f"{prefix}_bytes",
        f"{prefix}_filename",
        f"{prefix}_loaded_signature",
        f"{prefix}_df",
        f"{prefix}_profile",
        f"{prefix}_result_bytes",
        f"{prefix}_result_name",
        f"{prefix}_result_preview",
        f"{prefix}_result_metadata",
        f"{prefix}_selected_columns",
        *extra_keys,
    }
    for key in keys_to_clear:
        st.session_state.pop(key, None)


def sync_uploaded_file(prefix: str, uploaded_file, extra_keys: tuple[str, ...] = ()) -> tuple[bytes | None, str | None]:
    if uploaded_file is None:
        reset_module_state(prefix, extra_keys=extra_keys)
        return None, None

    data = uploaded_file_bytes(uploaded_file)
    signature = file_signature(data, uploaded_file.name)
    signature_key = f"{prefix}_signature"
    if st.session_state.get(signature_key) != signature:
        st.session_state[signature_key] = signature
        st.session_state[f"{prefix}_bytes"] = data
        st.session_state[f"{prefix}_filename"] = uploaded_file.name
        for key in extra_keys:
            st.session_state.pop(key, None)
        st.session_state.pop(f"{prefix}_result_bytes", None)
        st.session_state.pop(f"{prefix}_result_name", None)
        st.session_state.pop(f"{prefix}_result_preview", None)
        st.session_state.pop(f"{prefix}_result_metadata", None)
    return data, uploaded_file.name


def get_download_mime(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return MIME_MAP.get(suffix, "application/octet-stream")


def safe_process_error(prefix: str, action: str, exc: Exception) -> None:
    logger.exception("%s 处理失败", prefix)
    st.error(f"{action}失败: {exc}")


def render_analysis_tab() -> None:
    st.subheader("数据分析")
    st.caption("上传 CSV 或 Excel 文件，默认预览前 20 行，并生成可下载的 Excel 分析报告。")

    uploaded_file = st.file_uploader(
        "选择数据文件",
        type=["csv", "xlsx", "xlsm"],
        key="analysis_upload",
        help="支持 CSV、XLSX、XLSM。",
    )

    file_bytes, source_name = sync_uploaded_file(
        "analysis",
        uploaded_file,
        extra_keys=("analysis_report_bytes", "analysis_report_name"),
    )

    if file_bytes is None or source_name is None:
        st.info("请先上传一个 CSV 或 Excel 文件。")
        return

    try:
        if st.session_state.get("analysis_loaded_signature") != st.session_state.get("analysis_signature"):
            with st.spinner("正在读取数据文件..."):
                df = load_tabular_dataframe(file_bytes, source_name)
            st.session_state["analysis_df"] = df
            st.session_state["analysis_profile"] = get_table_profile(df)
            st.session_state["analysis_loaded_signature"] = st.session_state.get("analysis_signature")
            st.session_state.pop("analysis_report_bytes", None)
            st.session_state.pop("analysis_report_name", None)
            st.session_state.pop("analysis_result_preview", None)
    except Exception as exc:
        safe_process_error("数据分析模块", "读取文件", exc)
        return

    df = st.session_state.get("analysis_df")
    profile = st.session_state.get("analysis_profile")
    if df is None or profile is None:
        st.warning("文件尚未成功解析。")
        return

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("行数", profile["row_count"])
    metric_col2.metric("列数", profile["column_count"])
    metric_col3.metric("数值字段", len(profile["numeric_columns"]))

    st.markdown("**基础信息**")
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.write(f"文件名: {source_name}")
        st.write("字段名:")
        st.write(", ".join(profile["columns"]) if profile["columns"] else "无")
    with info_col2:
        numeric_columns = get_numeric_columns(df)
        st.write("数值字段:")
        st.write(", ".join(numeric_columns) if numeric_columns else "无")

    st.markdown("**数据预览**")
    st.dataframe(df.head(int(SETTINGS["max_preview_rows"])), use_container_width=True, height=360)

    st.markdown("**分析参数**")
    if numeric_columns := get_numeric_columns(df):
        selected_columns = st.multiselect(
            "选择一个或多个数值字段进行汇总",
            options=numeric_columns,
            default=numeric_columns,
            key="analysis_selected_columns",
        )
    else:
        selected_columns = []
        st.info("当前文件没有检测到数值字段，仍可生成概览和字段清单。")

    if st.button("生成 Excel 分析报告", key="analysis_generate_button", type="primary"):
        try:
            with st.spinner("正在生成 Excel 分析报告..."):
                report_bytes, report_name = build_analysis_report(df, selected_columns, source_name)
            st.session_state["analysis_result_bytes"] = report_bytes
            st.session_state["analysis_result_name"] = report_name
            st.success("分析报告已生成。")
        except Exception as exc:
            safe_process_error("数据分析模块", "生成报告", exc)

    report_bytes = st.session_state.get("analysis_result_bytes")
    report_name = st.session_state.get("analysis_result_name")
    if report_bytes and report_name:
        st.download_button(
            "下载 Excel 分析报告",
            data=report_bytes,
            file_name=report_name,
            mime=get_download_mime(report_name),
            use_container_width=True,
        )


def render_converter_tab() -> None:
    st.subheader("文件格式转写")
    st.caption("当前版本支持 PDF 转 TXT、Word 转 TXT、Excel 转 CSV、TXT 转 Word。输出结果可直接下载。")

    uploaded_file = st.file_uploader(
        "选择待转写文件",
        type=["pdf", "docx", "xlsx", "xlsm", "txt"],
        key="converter_upload",
        help="PDF、Word(.docx)、Excel(.xlsx/.xlsm)、TXT。",
    )

    file_bytes, source_name = sync_uploaded_file(
        "converter",
        uploaded_file,
        extra_keys=("converter_result_bytes", "converter_result_name", "converter_result_preview"),
    )

    if file_bytes is None or source_name is None:
        st.info("请先上传一个可转换的文件。")
        return

    conversion_label = get_conversion_label_for_file(source_name)
    if conversion_label is None:
        st.error("当前文件类型不在 MVP 支持范围内。")
        return

    st.write(f"识别到的转换方式: {conversion_label}")
    selected_conversion = st.selectbox(
        "转换类型",
        options=[conversion_label],
        key="converter_selected_conversion",
    )

    if st.button("开始处理", key="converter_generate_button", type="primary"):
        try:
            with st.spinner("正在转写或转换文件..."):
                result_bytes, result_name = convert_file(file_bytes, source_name, selected_conversion)
            st.session_state["converter_result_bytes"] = result_bytes
            st.session_state["converter_result_name"] = result_name

            result_suffix = Path(result_name).suffix.lower()
            if result_suffix in {".txt", ".csv"}:
                try:
                    st.session_state["converter_result_preview"] = result_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    st.session_state["converter_result_preview"] = result_bytes.decode("utf-8", errors="replace")
            else:
                st.session_state["converter_result_preview"] = ""
            st.success("文件已转换成功。")
        except Exception as exc:
            safe_process_error("文件格式转写模块", "转换文件", exc)

    result_bytes = st.session_state.get("converter_result_bytes")
    result_name = st.session_state.get("converter_result_name")
    result_preview = st.session_state.get("converter_result_preview", "")

    if result_bytes and result_name:
        result_suffix = Path(result_name).suffix.lower()
        if result_preview and result_suffix in {".txt", ".csv"}:
            st.markdown("**结果预览**")
            if result_suffix == ".csv":
                st.code(result_preview[:4000], language="csv")
            else:
                st.text_area("TXT 预览", value=result_preview[:4000], height=240)
        else:
            st.info("已生成可下载文件。")

        st.download_button(
            "下载转换结果",
            data=result_bytes,
            file_name=result_name,
            mime=get_download_mime(result_name),
            use_container_width=True,
        )


def render_image_tab() -> None:
    st.subheader("图片处理")
    st.caption("上传 JPG、PNG 或 WEBP 图片，设置目标宽高、输出格式和压缩质量，生成后可直接预览和下载。")

    uploaded_file = st.file_uploader(
        "选择图片文件",
        type=["jpg", "jpeg", "png", "webp"],
        key="image_upload",
        help="支持 JPG、PNG、WEBP。",
    )

    file_bytes, source_name = sync_uploaded_file(
        "image",
        uploaded_file,
        extra_keys=("image_result_bytes", "image_result_name", "image_result_metadata"),
    )

    if file_bytes is None or source_name is None:
        st.info("请先上传一张图片。")
        return

    parameter_col1, parameter_col2, parameter_col3 = st.columns(3)
    with parameter_col1:
        target_width = st.number_input(
            "目标宽度",
            min_value=1,
            max_value=10000,
            value=int(SETTINGS["default_image_width"]),
            step=1,
        )
    with parameter_col2:
        target_height = st.number_input(
            "目标高度",
            min_value=1,
            max_value=10000,
            value=int(SETTINGS["default_image_height"]),
            step=1,
        )
    with parameter_col3:
        output_format = st.selectbox(
            "输出格式",
            options=["JPG", "PNG", "WEBP"],
            index=0,
            key="image_output_format",
        )

    quality = st.slider(
        "压缩质量",
        min_value=1,
        max_value=100,
        value=int(SETTINGS["default_image_quality"]),
        help="JPG 和 WEBP 会直接使用该值。PNG 会自动映射为压缩级别。",
    )

    st.markdown("**原图预览**")
    st.image(file_bytes, caption=source_name, use_container_width=True)

    if st.button("开始处理图片", key="image_generate_button", type="primary"):
        try:
            with st.spinner("正在处理图片..."):
                result_bytes, result_name, metadata = process_image(
                    file_bytes=file_bytes,
                    source_name=source_name,
                    target_width=int(target_width),
                    target_height=int(target_height),
                    output_format=output_format,
                    quality=int(quality),
                )
            st.session_state["image_result_bytes"] = result_bytes
            st.session_state["image_result_name"] = result_name
            st.session_state["image_result_metadata"] = metadata
            st.success("图片已处理完成。")
        except Exception as exc:
            safe_process_error("图片处理模块", "处理图片", exc)

    result_bytes = st.session_state.get("image_result_bytes")
    result_name = st.session_state.get("image_result_name")
    metadata = st.session_state.get("image_result_metadata", {})

    if result_bytes and result_name:
        st.markdown("**处理后预览**")
        st.image(result_bytes, caption=result_name, use_container_width=True)

        if metadata:
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            meta_col1.metric("原始尺寸", f"{metadata['original_size'][0]} × {metadata['original_size'][1]}")
            meta_col2.metric("输出尺寸", f"{metadata['processed_size'][0]} × {metadata['processed_size'][1]}")
            meta_col3.metric("输出格式", metadata["output_format"])

        st.download_button(
            "下载处理后的图片",
            data=result_bytes,
            file_name=result_name,
            mime=get_download_mime(result_name),
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title=SETTINGS["app_title"],
        page_icon="A",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_page_style()
    render_header()

    tabs = st.tabs(["数据分析", "文件格式转写", "图片处理"])
    with tabs[0]:
        render_analysis_tab()
    with tabs[1]:
        render_converter_tab()
    with tabs[2]:
        render_image_tab()


if __name__ == "__main__":
    main()
