#!/bin/bash

SCRIPT_PATH=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../" && pwd)

PROJECT_CONFIG="$PROJECT_ROOT/configs/magic-pdf.json"
HOME_CONFIG="$HOME/magic-pdf.json"

echo "--- Expert: DocParser (MinerU) Smart & Clean ---"
echo "[Debug] Project Root: $PROJECT_ROOT"

if [ ! -f "$PROJECT_CONFIG" ]; then
    echo "[Error] Cannot find $PROJECT_CONFIG"
    echo "Please verify the file exists in AcademicAgent-Suite/configs/"
    exit 1
fi

cp "$PROJECT_CONFIG" "$HOME_CONFIG"
echo "[Status] Config deployed to $HOME_CONFIG"

trap 'rm -f "$HOME_CONFIG"; echo "[Status] Cleanup: Removed $HOME_CONFIG from home.";' EXIT

CONFIG_YAML="$PROJECT_ROOT/configs/model_config.yaml"
RAW_DIR=$(yq e '.paths.raw_storage' "$CONFIG_YAML")/PDF
PROCESSED_DIR=$(yq e '.paths.processed_storage' "$CONFIG_YAML")
CONDA_ENV_PY=$(yq e '.environments.doc_parser' "$CONFIG_YAML")
MAGIC_PDF_BIN=$(dirname "$CONDA_ENV_PY")/magic-pdf

shopt -s nullglob
pdf_files=("$RAW_DIR"/*.pdf)

if [ ${#pdf_files[@]} -eq 0 ]; then
    echo "[Exit] No PDF files found in $RAW_DIR"
    exit 0
fi

for pdf in "${pdf_files[@]}"; do
    filename_no_ext=$(basename "$pdf" .pdf)
    
    CHECK_PATH="$PROCESSED_DIR/magic-pdf/$filename_no_ext/ocr"
    
    if [ -d "$CHECK_PATH" ]; then
        echo "[Skip] $filename_no_ext already processed. Skipping..."
        continue
    fi

    echo "------------------------------------------------"
    echo "[Task] Processing: $filename_no_ext"

    "$MAGIC_PDF_BIN" pdf --pdf "$pdf" --method ocr
    
    if [ $? -eq 0 ]; then
        echo "[Success] Finished: $filename_no_ext"
    else
        echo "[Error] Failed to process $filename_no_ext"
    fi
done

echo "------------------------------------------------"
echo "--- DocParser Task Completed ---"