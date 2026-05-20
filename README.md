# AI Office Automation Web

一个可直接部署到互联网的 Streamlit MVP。用户打开网址后可以上传文件、处理文件、下载结果，不需要安装 Python，也不需要安装任何本地软件。

## 功能概览

### 1. 数据分析模块

- 上传 Excel 或 CSV
- 默认预览前 20 行
- 显示行数、列数、字段名、数值字段
- 选择一个或多个数值字段做汇总
- 生成 Excel 分析报告并下载

### 2. 文件格式转写模块

- PDF 转 TXT
- Word 转 TXT
- Excel 转 CSV
- TXT 转 Word
- 生成转换后的文件并下载

### 3. 图片处理模块

- 上传 JPG、PNG、WEBP
- 设置目标宽度和高度
- 选择输出格式 JPG、PNG、WEBP
- 设置压缩质量
- 单张图片处理
- 预览和下载结果

## 技术栈

- Python
- Streamlit
- pandas
- openpyxl
- xlrd
- python-docx
- pypdf
- Pillow

## 目录结构

```text
ai-office-automation-web/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ packages.txt
├─ render.yaml
├─ modules/
│  ├─ data_analysis/
│  │  ├─ analyzer.py
│  │  └─ __init__.py
│  ├─ file_converter/
│  │  ├─ converter.py
│  │  └─ __init__.py
│  └─ image_processor/
│     ├─ processor.py
│     └─ __init__.py
├─ services/
│  ├─ file_service.py
│  └─ log_service.py
├─ config/
│  └─ settings.json
└─ .streamlit/
   └─ config.toml
```

## Mac 本地运行

### 1. 进入项目目录

```bash
cd ai-office-automation-web
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 启动网页

```bash
streamlit run app.py
```

浏览器会打开本地网页地址，Mac 上直接在浏览器里使用即可。

## 上传到 GitHub

### 方式一，命令行

```bash
git init
git add .
git commit -m "Initial MVP"
git branch -M main
git remote add origin https://github.com/<your-name>/ai-office-automation-web.git
git push -u origin main
```

### 方式二，GitHub Desktop

1. 打开 GitHub Desktop
2. 选择当前项目文件夹
3. 提交初始版本
4. 发布到 GitHub 仓库

## 部署到 Streamlit Community Cloud

1. 先把代码推送到 GitHub
2. 打开 Streamlit Community Cloud
3. 选择 `New app`
4. 选中你的 GitHub 仓库和 `main` 分支
5. 主文件选择 `app.py`
6. 点击部署

因为这个项目只使用纯 Python 依赖，没有系统级依赖，所以部署会比较简单。`packages.txt` 不是必需文件，可以保留为空，也可以不放。

## 部署到 Render

1. 把代码推送到 GitHub
2. 打开 Render
3. 直接用 `render.yaml` 创建 Blueprint 服务，或者新建 `Web Service`
4. 连接你的 GitHub 仓库
5. Build Command:

```bash
pip install -r requirements.txt
```

6. Start Command:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

7. 保存并部署

如果使用 `render.yaml`，Render 会自动读取构建和启动命令，部署会更直接。

## 云端使用限制

- PDF 转 TXT 只提取文本层，不做 OCR，所以扫描版 PDF 可能提取不到内容
- Word 转 TXT 仅支持 `.docx`，不支持老式 `.doc`
- Excel 支持 `.xls`、`.xlsx`、`.xlsm`，Excel 转 CSV 仅转换第一个工作表
- 图片处理是单张图片处理
- 当前 Streamlit 上传上限配置为 500MB，但大 Excel 文件会被 pandas 整体读入内存，实际可处理大小仍受 Render 实例内存限制
- 图片会按目标宽高生成，MVP 使用等比缩放加居中填充，避免拉伸变形

## 推荐的后续扩展

- 增加批量处理
- 增加 OCR
- 增加多工作表 Excel 转换
- 增加更多报告模板
- 增加用户登录和任务历史
