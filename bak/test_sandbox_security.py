"""
测试策略执行沙箱的安全性

运行方式：
cd backend_api_python
python scripts/test_sandbox_security.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.safe_exec import safe_exec_code, validate_code_safety
import pandas as pd
import numpy as np


def test_case(name: str, code: str, should_block: bool = True):
    """测试单个攻击案例"""
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"预期: {'应该被阻止' if should_block else '应该允许执行'}")
    print(f"{'='*60}")
    print(f"代码:\n{code}\n")
    
    # 1. 静态检查
    is_safe, error_msg = validate_code_safety(code)
    print(f"[静态检查] {'✓ 通过' if is_safe else '✗ 拦截'}")
    if not is_safe:
        print(f"  原因: {error_msg}")
        if should_block:
            print("  ✓ 正确拦截")
        else:
            print("  ✗ 误报（不应该拦截）")
        return
    
    # 2. 运行时执行
    exec_globals = {
        'pd': pd,
        'np': np,
        'df': pd.DataFrame({'close': [100, 101, 102]}),
    }
    
    result = safe_exec_code(
        code=code,
        exec_globals=exec_globals,
        timeout=5
    )
    
    print(f"[运行时] {'✓ 执行成功' if result['success'] else '✗ 执行失败'}")
    if not result['success']:
        print(f"  错误: {result['error'][:200]}")
        if should_block:
            print("  ✓ 正确拦截")
        else:
            print("  ✗ 误报（不应该失败）")
    else:
        if should_block:
            print("  ✗✗✗ 安全漏洞！恶意代码执行成功！")
        else:
            print("  ✓ 正常执行")
        
        # 检查是否有输出
        if 'result' in exec_globals:
            print(f"  结果: {exec_globals['result']}")


def run_all_tests():
    """运行所有安全测试"""
    
    print("\n" + "="*60)
    print("策略执行沙箱安全性测试")
    print("="*60)
    
    # ============ 基础攻击测试 ============
    
    test_case(
        "1. 直接导入 os 模块",
        """
import os
result = os.system('echo "hacked"')
""",
        should_block=True
    )
    
    test_case(
        "2. 使用 subprocess 执行命令",
        """
import subprocess
result = subprocess.run(['ls', '-la'], capture_output=True)
""",
        should_block=True
    )
    
    test_case(
        "3. 使用 eval 执行代码",
        """
result = eval("__import__('os').system('ls')")
""",
        should_block=True
    )
    
    test_case(
        "4. 使用 exec 执行代码",
        """
exec("import os; os.system('ls')")
""",
        should_block=True
    )
    
    test_case(
        "5. 直接使用 __import__",
        """
os = __import__('os')
result = os.system('ls')
""",
        should_block=True
    )
    
    test_case(
        "6. 使用 open 读取文件",
        """
with open('/etc/passwd', 'r') as f:
    result = f.read()
""",
        should_block=True
    )
    
    # ============ 高级绕过测试 ============
    
    test_case(
        "7. 通过 __builtins__ 访问 __import__",
        """
result = __builtins__['__import__']('os').system('ls')
""",
        should_block=True
    )
    
    test_case(
        "8. 通过 getattr 绕过检测",
        """
import builtins
os = getattr(builtins, '__import__')('os')
result = os.system('ls')
""",
        should_block=True
    )
    
    test_case(
        "9. 通过类继承链逃逸 (经典沙箱逃逸)",
        """
# 获取 object 类
obj = ().__class__.__bases__[0]
# 获取所有子类
subclasses = obj.__subclasses__()
# 查找可用的危险类
result = [x.__name__ for x in subclasses if 'warning' in x.__name__.lower()]
""",
        should_block=True
    )
    
    test_case(
        "10. 通过 Popen 类执行命令",
        """
# 尝试找到 subprocess.Popen 类
for cls in ().__class__.__bases__[0].__subclasses__():
    if cls.__name__ == 'Popen':
        result = cls(['ls', '-la'])
        break
""",
        should_block=True
    )
    
    test_case(
        "11. 通过 globals() 访问全局变量",
        """
g = globals()
result = list(g.keys())
""",
        should_block=True
    )
    
    test_case(
        "12. 通过 locals() 访问局部变量",
        """
l = locals()
result = list(l.keys())
""",
        should_block=True
    )
    
    test_case(
        "13. 通过 dir() 探测可用对象",
        """
result = dir()
""",
        should_block=True
    )
    
    test_case(
        "14. 通过 type() 创建新类型",
        """
NewClass = type('NewClass', (), {'__init__': lambda self: __import__('os')})
result = NewClass()
""",
        should_block=True
    )
    
    test_case(
        "15. 通过字符串拼接绕过关键字检测",
        """
module_name = 'o' + 's'
os = __import__(module_name)
result = os.system('ls')
""",
        should_block=True
    )
    
    # ============ 资源耗尽攻击 ============
    
    test_case(
        "16. 无限循环 (应该超时)",
        """
while True:
    pass
""",
        should_block=True
    )
    
    test_case(
        "17. 内存炸弹",
        """
# 尝试分配大量内存
result = [1] * (10**8)  # 100M 个整数
""",
        should_block=True
    )
    
    test_case(
        "18. 递归炸弹",
        """
def bomb():
    return bomb()
result = bomb()
""",
        should_block=True
    )
    
    # ============ 合法代码测试 ============
    
    test_case(
        "19. 正常的 pandas 操作 (应该允许)",
        """
df['sma'] = df['close'].rolling(window=2).mean()
result = df['sma'].iloc[-1]
""",
        should_block=False
    )
    
    test_case(
        "20. 正常的 numpy 操作 (应该允许)",
        """
arr = np.array([1, 2, 3, 4, 5])
result = np.mean(arr)
""",
        should_block=False
    )
    
    test_case(
        "21. 使用 hasattr 检查属性 (应该允许)",
        """
result = hasattr(df, 'close')
""",
        should_block=False
    )
    
    test_case(
        "22. 导入允许的模块 (应该允许)",
        """
import math
import json
from datetime import datetime
result = math.sqrt(16)
""",
        should_block=False
    )
    
    # ============ 边界情况测试 ============
    
    test_case(
        "23. 访问 pandas 内部属性",
        """
# 尝试通过 pandas 对象访问危险功能
result = df.__class__.__module__
""",
        should_block=False  # 这个可能需要阻止，但目前可能会通过
    )
    
    test_case(
        "24. 使用 lambda 和 map",
        """
result = list(map(lambda x: x * 2, [1, 2, 3]))
""",
        should_block=False
    )
    
    test_case(
        "25. 列表推导式中的类型反射",
        """
result = [x for x in ().__class__.__bases__]
""",
        should_block=True  # 应该阻止，但可能会通过
    )
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == '__main__':
    run_all_tests()
