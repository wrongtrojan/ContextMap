#!/bin/bash

# 参数校验
if [ "$#" -ne 2 ]; then
    echo "[Usage] $0 <asset_id> <pdf_path>"
    exit 1
fi

ASSET_ID=$1
PDF_PATH=$2

SCRIPT_PATH=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
# 假设项目根目录在 services/.. 的上一级
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../" && pwd)

PROJECT_CONFIG="$PROJECT_ROOT/configs/magic-pdf.json"
HOME_CONFIG="$HOME/magic-pdf.json"
CONFIG_YAML="$PROJECT_ROOT/configs/model_config.yaml"

# 1. 配置文件部署 (MinerU 强制要求在用户根目录有配置文件)
if [ -f "$PROJECT_CONFIG" ]; then
    cp "$PROJECT_CONFIG" "$HOME_CONFIG"
fi

# 2. 环境与路径解析
# 使用 yq 获取配置（需确保系统安装了 yq）
PROCESSED_ROOT=$(yq e '.paths.processed_storage' "$CONFIG_YAML")
CONDA_ENV_PY=$(yq e '.environments.doc_parser' "$CONFIG_YAML")
MAGIC_PDF_BIN=$(dirname "$CONDA_ENV_PY")/magic-pdf

# 定义输出目录：processed_storage/magic-pdf/{asset_id}
OUTPUT_DIR="$PROCESSED_ROOT/magic-pdf/$ASSET_ID"
mkdir -p "$OUTPUT_DIR"

echo "[Task] Processing Asset: $ASSET_ID"
echo "[Path] Source: $PDF_PATH"
echo "[Path] Target: $OUTPUT_DIR"

# 3. 执行转换
# --output_dir 指定输出位置，--method ocr 强制 OCR
"$MAGIC_PDF_BIN" pdf --pdf "$PDF_PATH" --output_dir "$OUTPUT_DIR" --method ocr

EXIT_CODE=$?

# 4. 清理环境配置
rm -f "$HOME_CONFIG"

if [ $EXIT_CODE -eq 0 ]; then
    echo "[Success] Asset $ASSET_ID processed."
    exit 0
else
    echo "[Error] MinerU failed with exit code $EXIT_CODE"
    exit 1
fi