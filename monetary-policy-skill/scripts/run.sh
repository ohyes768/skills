#!/bin/bash
# 货币政策数据获取脚本

SCRIPT_DIR="$(dirname "$0")"

# 默认获取当前月份数据
MONTH=$(date +%Y-%m)

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --month)
            MONTH="$2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "正在获取 ${MONTH} 的货币政策指标数据..."
cd "$SCRIPT_DIR"
python run_all.py --month "$MONTH"
