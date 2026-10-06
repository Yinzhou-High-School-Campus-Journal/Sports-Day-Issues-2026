#!/usr/bin/env sh
# 兼容旧入口；使用当前虚拟环境与仓库锁定的 Playwright。
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/build.py" "$@"
