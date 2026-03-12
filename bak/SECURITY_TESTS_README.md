# 策略执行沙箱安全性测试

## 概述

这些测试脚本用于验证策略代码执行环境的安全性，检测可能的沙箱逃逸、库修改和资源耗尽攻击。

## 测试文件

1. **test_sandbox_security.py** - 基础沙箱安全性测试
   - 测试各种沙箱逃逸技巧
   - 验证静态代码检查和运行时保护
   - 包含 25 个测试用例

2. **test_library_modification.py** - 库修改攻击测试
   - 测试是否可以修改 pandas/numpy 等共享库
   - 验证猴子补丁（Monkey Patching）攻击
   - 测试状态污染问题

## 运行测试

### 方式 1: 单独运行

```bash
cd backend_api_python

# 测试基础沙箱安全性
python scripts/test_sandbox_security.py

# 测试库修改攻击
python scripts/test_library_modification.py
```

### 方式 2: 运行所有测试

```bash
cd backend_api_python
bash scripts/run_security_tests.sh
```

或者在 Windows 上：

```bash
cd backend_api_python
python scripts/test_sandbox_security.py
python scripts/test_library_modification.py
```

## 测试内容

### 基础攻击测试
- ✓ 直接导入危险模块（os, subprocess）
- ✓ 使用 eval/exec 执行代码
- ✓ 使用 __import__ 导入模块
- ✓ 文件操作（open, read, write）

### 高级绕过测试
- ✓ 通过 __builtins__ 访问危险函数
- ✓ 通过 getattr 绕过检测
- ✓ 类继承链逃逸（经典沙箱逃逸）
- ✓ 通过 Popen 类执行命令
- ✓ 通过 globals()/locals() 访问变量
- ✓ 字符串拼接绕过关键字检测

### 资源耗尽攻击
- ✓ 无限循环（超时测试）
- ✓ 内存炸弹
- ✓ 递归炸弹

### 库修改攻击
- ✓ 修改 pandas.DataFrame 行为
- ✓ 修改 numpy 函数
- ✓ 猴子补丁劫持方法
- ✓ 状态污染（影响其他策略）

## 预期结果

### 安全的沙箱应该：
- ✓ 阻止所有危险操作（标记为 "应该被阻止" 的测试）
- ✓ 允许正常的 pandas/numpy 操作
- ✓ 防止库修改和状态污染
- ✓ 在超时时间内终止恶意代码

### 如果出现 ✗✗✗ 标记：
说明存在严重的安全漏洞，恶意代码可以：
1. 执行系统命令
2. 读写文件
3. 修改共享库的行为
4. 影响其他策略的执行
5. 耗尽系统资源

## 已知问题

当前沙箱实现存在以下限制：

1. **Windows 平台**：超时机制不工作（signal.alarm 不支持）
2. **非主线程**：超时机制不工作
3. **内存限制**：默认关闭（需要设置 SAFE_EXEC_ENABLE_RLIMIT=true）
4. **共享进程**：策略在 Flask 主进程中执行，可能相互影响
5. **库修改**：可能可以修改 pandas/numpy 的行为

## 改进建议

### 短期方案（快速修复）
1. 增强 AST 检查，阻止更多危险模式
2. 启用内存限制（设置环境变量）
3. 添加用户权限系统，限制谁可以执行自定义策略

### 中期方案（推荐）
1. 使用 multiprocessing 在独立进程中执行策略
2. 每次执行前重新导入库（防止污染）
3. 使用 RestrictedPython 替代当前实现

### 长期方案（最安全）
1. 使用 Docker 容器完全隔离每个策略执行
2. 实现代码审核机制
3. 建立策略市场，只允许审核通过的策略

## 相关文件

- `app/utils/safe_exec.py` - 安全执行工具
- `app/services/backtest.py` - 回测服务（调用策略执行）
- `app/services/strategy_compiler.py` - 策略编译器

## 参考资料

- [Python 沙箱逃逸技巧](https://book.hacktricks.xyz/generic-methodologies-and-resources/python/bypass-python-sandboxes)
- [RestrictedPython 文档](https://restrictedpython.readthedocs.io/)
- [OWASP Code Injection](https://owasp.org/www-community/attacks/Code_Injection)
