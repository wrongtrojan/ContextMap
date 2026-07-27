# ContextMap environment setup

Python 依赖、系统工具、密钥与首次启动的详细说明。快速上手见根目录 [README.md](../README.md)。

---

## 1. 系统依赖

| 工具 | 必需 | 用途 |
|------|------|------|
| Docker + Compose | 是 | Postgres (`5432`)、MinIO (`9000` / console `9001`) |
| Conda + Python **3.11** | 是 | 后端运行时 |
| Node.js **20+** + npm | 是 | `web/frontend` Workbench |
| **ffmpeg** | 视频/音频 | 须在 `PATH` 中；Ubuntu: `sudo apt install ffmpeg` |
| **MinerU** | PDF | 已随默认 requirements 安装 |
| NVIDIA + CUDA | 可选 | `infer.visual`、AutoRE KG；无 GPU 见 §4 校准 |

### 平台说明

- **Linux（Ubuntu 22.04+）**：主要开发与部署目标。
- **Windows 原生**：FastAPI / 前端可跑；`vLLM`、`flash-attn` 不支持 Windows，视觉推理需关闭或改用 WSL2 Ubuntu。
- **macOS**：可跑 UI + API；本地 CUDA 视觉推理不可用，建议 `infer.visual.enabled: false`。

远程开发常见拓扑：**GPU 服务器跑后端**，本机浏览器或 [`desktop/`](../desktop/) Electron 壳连 `http://服务器:3000`，前端 build/dev 时设置：

```bash
export NEXT_PUBLIC_API_BASE_URL=http://服务器IP:8000
```

---

## 2. Python 环境

### conda 环境的创建与职责

| 环境名 | 创建 | 作用 | 何时必须 |
|------|------|------|------|
| `ContextMap` | 手动 `conda create -n ContextMap ...` 创建 | 主服务环境（FastAPI、检索、评估、前端联调命令） | 一直必须 |
| `infer-sandbox` | `conda env create -f environment/infer-sandbox.yaml` 创建 | 科学沙盒子进程隔离环境 | 仅当 `infer.sandbox.enabled: true` |

```bash
conda create -n ContextMap python=3.11
conda activate ContextMap
python -m pip install -r environment/requirements-dev.txt
```

- `requirements.base.txt`：API / DB / storage 基础依赖。
- `requirements.ml.txt`：embedding / whisper / reranker / autore 运行依赖。
- `requirements.visual.txt`：视觉推理依赖（vLLM / qwen-vl-utils）。
- `requirements.txt`：聚合入口（base + ml + visual）。
- `requirements-dev.txt`：在聚合入口上追加 pytest / httpx。
- MinerU（PDF 解析）已并入 `requirements.ml.txt`，默认随主环境安装。
- **`flash-attn`**：仅非 Windows；安装失败时可跳过，并关闭 visual infer。
- **`bitsandbytes`**：Windows 支持有限；KG / 4bit 加载建议在 Linux + CUDA 上使用。

### Infer sandbox（独立 conda，可选）

科学计算沙盒 `services/infer/sandbox` 使用隔离环境，**不含**主环境的 torch：

```bash
conda env create -f environment/infer-sandbox.yaml
```

环境名须与 `configs/contextmap.yaml` → `infer.sandbox.conda_env` 一致（默认 `infer-sandbox`）。

---

## 3. 配置与密钥

### 主配置

[`configs/contextmap.yaml`](../configs/contextmap.yaml) — 数据库、MinIO、模型目录、流水线并发、检索 / infer 开关等。

### 密钥（勿提交 Git）

| 方式 | 路径 / 说明 |
|------|-------------|
| **推荐** | Workbench → Settings → Save（写入 YAML + secrets） |
| 手动 | `storage/local/secrets.env` |
| CI / Docker | 进程环境变量 |


### 环境变量

| Variable | Used by | Default (if unset) |
|----------|---------|-------------------|
| `DEEPSEEK_API_KEY` | outline LLM、chat | 无（LLM 功能必需） |
| `POSTGRES_PASSWORD` | `database/config.py` | `contextmap`（与 yaml 一致） |
| `MINIO_SECRET_KEY` | MinIO 客户端 | `contextmap123` |
| `HF_ENDPOINT` | AutoRE LoRA 下载 | HuggingFace 官方；国内可设 `https://hf-mirror.com` |
| `NEXT_PUBLIC_API_BASE_URL` | 前端 API 根地址 | `http://localhost:8000` |
| `LIVE_ENABLE_INFER` | live E2E 测试 | 未设则 live 测试跳过 infer |

Docker Compose（[`deploy/docker-compose.yml`](../deploy/docker-compose.yml)）中 Postgres / MinIO 账号与 `contextmap.yaml` 对齐。

---

## 4. 首次启动清单

```bash
conda activate ContextMap
cd /path/to/ContextMap

python -m pip install -r environment/requirements-dev.txt

# 基础设施 + 校准 + core 模型 + 可选 API Key
python contextmap.py setup --apply-calibrate -y

# 前端依赖（serve all 之前必做）
cd web/frontend && npm install && cd ../..

python contextmap.py doctor
python contextmap.py serve all
```

分步等价命令：

```bash
python contextmap.py docker up
python contextmap.py models download --profile core -y
python contextmap.py calibrate --apply
python contextmap.py serve all
```

遗留包装脚本仍可用：

- `bash deploy/installer.sh` → 仅 Docker + 目录（等同 `setup --skip-models --skip-secrets --skip-calibrate`）
- `bash models/downloader.sh` → 等同 `models download --profile core`

### GPU / CPU 校准

```bash
python contextmap.py calibrate          # 查看建议
python contextmap.py calibrate --apply  # 写入 contextmap.yaml
```

无 CUDA 时典型结果：`embedding` / `reranker` → `cpu`，`infer.visual.enabled` → `false`。有 GPU 时可将 visual / KG 设备设为 `cuda`。

### 模型预下载档位

```bash
python contextmap.py models download --profile core -y
python contextmap.py models status
python contextmap.py models download --section visual -y   # 单个模型
```

| Profile | Models |
|---------|--------|
| `minimal` | BGE-M3 embedding、faster-whisper |
| `core` | + BGE reranker（**默认**，doctor 检查此项） |
| `full` | + Qwen2-VL-7B-Instruct |
| `kg` | AutoRE Mistral-7B + LoRA（`kg.enabled: true` 时需要） |
| `all` | 以上全部 |

权重目录在 `models/` 下，大目录已 `.gitignore`，需在本机或服务器本地下载。

---

## 5. 服务端口

| 服务 | 端口 | 启动方式 |
|------|------|----------|
| FastAPI 后端 | 8000 | `python contextmap.py serve backend` |
| Next.js 前端 | 3000 | `python contextmap.py serve frontend` |
| Postgres | 5432 | `python contextmap.py docker up` |
| MinIO API / Console | 9000 / 9001 | 同上 |
| Adminer | 8080 | 同上（可选 DB 管理 UI） |

---

## 6. 常见问题

**`npm start` 报 `BUILD_ID` 不存在**  
先执行 `npm run build`，开发阶段用 `npm run dev` 或 `python contextmap.py serve frontend`。

**`doctor` 报模型缺失**  
运行 `python contextmap.py models download --profile core -y`。AutoRE 仅在开启 KG 时需要：`--profile kg`。

**PDF 上传后 parse 失败**  
确认 `python -m pip install -r environment/requirements-dev.txt` 已成功（其中已含 MinerU），并查看资产状态中的 `error_message`。

**视频处理报 ffmpeg**  
安装 ffmpeg 并确认 `which ffmpeg` 有输出。

**视觉推理 / vLLM 安装或启动失败**  
`python contextmap.py calibrate --apply` 关闭 visual；主流程在 `infer.fail_open: true` 下仍可完成对话。

**Electron `Missing X server`**  
在无桌面环境的 SSH 服务器上无法启动；在有 GUI 的本机运行 `desktop/`，`config.json` 指向已部署的前端 URL。

---

## 7. 运行测试

```bash
conda activate ContextMap
pytest
```

Live E2E（需 API Key、可选 GPU）见 `tests/test_chats_e2e_live*.py` 及 `LIVE_ENABLE_INFER` 说明。
