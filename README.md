# ContextMap

<p>
    <a href="#"><img src="https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="http://choosealicense.com/licenses/mit/"><img src="https://img.shields.io/badge/license-MIT-2E7D32?style=flat-square&logo=bookstack&logoColor=white" alt="License"></a>
    <a href="#"><img src="https://img.shields.io/badge/AI--Agent-ContextMap-008080?style=flat-square&logo=openai&logoColor=white" alt="AI-Agent"></a>
    <a href="#"><img src="https://img.shields.io/badge/Linux-Ubuntu-333333?style=flat-square&logo=linux&logoColor=white" alt="Linux"></a>
    <a href="#"><img src="https://img.shields.io/badge/Container-Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></a>
</p>

*一个多模态解析资料 (PDF/视频/音频), 生成结构化大纲, 溯源证据并进行增强验证 (科学沙盒 / 视觉推理) 的 Agent。*

---

## 📸 Screenshots

(上个版本的截图，仅供参考)

| Uploading | Handling |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_uploading.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_handling.png) |

| Structural Outline - PDF | Structural Outline - Video |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_structuraloutline1.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_structuraloutline2.png) |

| Querying | Finalizing |
| --- | --- |
| ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_querying.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_finalizing.png) |

| Chat Session | Evidence Trace |
| --- | --- |
|![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_chatsession.png) | ![](https://cdn.jsdelivr.net/gh/wrongtrojan/bed@main/ContextMap/Screenshot_evidencetrace.png) |

---

## 💻 Quickstart

### 环境

- `ContextMap`（主环境）：运行 FastAPI、检索/评估/推理主流程、CLI 工具。
- `infer-sandbox`（子环境）：仅用于科学计算沙盒子进程，最小依赖（`numpy` + `sympy`），与主环境隔离，避免污染主运行时。

`configs/contextmap.yaml` 中 `infer.sandbox.conda_env` 默认指向 `infer-sandbox`；关闭 `infer.sandbox.enabled` 时可不创建该子环境。

### 前置依赖

| 组件 | 用途 | 说明 |
|------|------|------|
| **Docker + Compose** | Postgres、MinIO | 当前用户需在 `docker` 组，或具备运行 Docker 的权限 |
| **Conda** | Python 3.11 主环境 | 推荐 Miniconda / Mambaforge |
| **Node.js 20+** | Next.js Workbench | 前端 dev / build 必需 |
| **ffmpeg** | 视频解析 | 系统安装并加入 `PATH`（`sudo apt install ffmpeg`） |
| **NVIDIA GPU**（可选） | 视觉推理、KG | 无 GPU 时可用 CPU + API，见下方校准说明 |


更完整的环境说明、Windows/WSL 注意项见 [`environment/README.md`](environment/README.md)。

### 1. 克隆与 Python 环境

```bash
git clone https://github.com/wrongtrojan/ContextMap.git
cd ContextMap

conda create -n ContextMap python=3.11
conda activate ContextMap
pip install -r environment/requirements-dev.txt
```

> **安装提示**：`flash-attn` / `vLLM` 仅面向 Linux + CUDA。CPU 机器或安装失败时，运行 `python contextmap.py calibrate --apply` 会自动关闭 `infer.visual` 并改用 CPU 设备；聊天与 API 大纲仍可用。

### 依赖分层（统一规范）

- `environment/requirements.base.txt`：API / DB / Storage 基础依赖。
- `environment/requirements.ml.txt`：embedding / whisper / reranker / autore 运行依赖。
- `environment/requirements.visual.txt`：视觉推理（vLLM）依赖，偏 Linux+CUDA。
- MinerU（PDF 解析）已并入 `environment/requirements.ml.txt`，默认随 `requirements-dev.txt` 安装。
- `environment/requirements.txt`：聚合入口（base + ml + visual）。
- `environment/requirements-dev.txt`：开发与测试依赖（在 requirements 之上叠加）。

### 2. 基础设施与模型

```bash
# 一键：Docker 栈 + GPU/CPU 校准 + 可选 API Key + 预下载 core 模型
python contextmap.py setup --apply-calibrate -y

# 或分步：
python contextmap.py docker up
python contextmap.py models download --profile core -y
python contextmap.py calibrate --apply
```

**模型档位**（首次下载较慢，建议提前执行）：

| Profile | 内容 | 大致体积 |
|---------|------|----------|
| `minimal` | embedding + whisper | ~5 GB |
| `core`（默认） | + reranker | ~7 GB |
| `full` | + Qwen2-VL-7B 视觉推理 | ~23 GB |
| `kg` | AutoRE（KG 抽取，当前默认关闭） | ~15 GB |

等价脚本：`bash models/downloader.sh`（默认 `core`）。

### 3. 密钥与配置

**不要**再使用仓库根目录的 `.env`。密钥与可调参数入口：

| 文件 / 入口 | 作用 |
|-------------|------|
| [`configs/contextmap.yaml`](configs/contextmap.yaml) | 数据库、模型路径、流水线并发、infer 开关等 |
| `storage/local/secrets.env` | `DEEPSEEK_API_KEY` 等密钥（**已 gitignore**，勿提交） |
| Workbench → **Settings** 标签页 | UI 写入上述 YAML + secrets，保存即落盘 |

```bash
# setup 时交互输入，或手动写入：
# storage/local/secrets.env
# DEEPSEEK_API_KEY=sk-...
```

### 4. 前端与启动

```bash
cd web/frontend && npm install && cd ../..

# 健康检查（Docker、端口、core 模型、API Key）
python contextmap.py doctor

# 同时启动后端 (8000) + 前端 dev (3000)
python contextmap.py serve all
```

浏览器打开 **http://localhost:3000**。分开启动：

```bash
python contextmap.py serve backend    # uvicorn :8000
python contextmap.py serve frontend   # next dev :3000
```

生产模式前端需先 build：`cd web/frontend && npm run build && npm run start`（不要用仅有 dev 缓存的 `.next` 直接 `start`）。

### 5. 科学沙盒（可选）

```bash
conda env create -f environment/infer-sandbox.yaml
# 环境名须与 configs/contextmap.yaml 中 infer.sandbox.conda_env 一致（默认 infer-sandbox）
```

### 6. 桌面壳（可选）

在有图形界面的本机运行 Electron，后端可仍在远程服务器：

```bash
cd desktop && npm install
cp config.example.json config.json   # appUrl 指向 http://127.0.0.1:3000 或远程地址
npm start
```

详见 [`desktop/config.example.json`](desktop/config.example.json)。SSH 无显示器的服务器上无法直接跑 Electron。

---

## 🧰 CLI 速查

根目录 [`contextmap.py`](contextmap.py)（或 `./contextmap`）：

```bash
python contextmap.py setup [--apply-calibrate] [-y]   # 首次初始化
python contextmap.py models download --profile core -y
python contextmap.py models status
python contextmap.py calibrate [--apply]
python contextmap.py doctor
python contextmap.py docker up|down|status
python contextmap.py serve all|backend|frontend
```

---

## 🛠️ Features

**📑 多模态解析**

| PDF处理 | 视频处理 |
| --- | --- |
|支持含复杂的表格/公式/双栏PDF的解析|自动提取视频关键帧/转录语音并对齐|

<br>

**🗺️ 结构化大纲**

| 逻辑层级重构 | 精准跳转 |
| --- | --- |
|将冗长资料重组为层级清晰的思维大纲|支持页数(PDF)/时间戳(视频)精准跳转|

<br>

**🚀 增强验证**

| 科学沙盒 | 视觉推理 |
| --- | --- |
|验证数学/物理/计算机公式/算法准确性|验证复杂表格/图表/视频关键帧帧语义|

<br>

**📍 证据回溯**

| PDF | 视频 |
| --- | --- |
|定位至PDF的具体页码与高亮段落(点击跳转)|定位至视频对应时间戳(点击跳转)|

---

