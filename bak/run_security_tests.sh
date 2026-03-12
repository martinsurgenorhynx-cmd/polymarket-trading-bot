#!/bin/bash

# 运行所有安全测试

echo "=================================="
echo "策略执行沙箱安全性测试套件"
echo "=================================="
echo ""

cd "$(dirname "$0")/.."

echo "测试 1: 基础沙箱安全性"
echo "----------------------------------"
python scripts/test_sandbox_security.py
echo ""

echo ""
echo "测试 2: 库修改攻击"
echo "----------------------------------"
python scripts/test_library_modification.py
echo ""

echo ""
echo "=================================="
echo "所有测试完成"
echo "=================================="
