"""
测试是否可以修改已导入的库（pandas, numpy等）

这是一个严重的安全问题：如果恶意代码可以修改共享库的行为，
会影响同一进程中的其他策略执行。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.safe_exec import safe_exec_code, validate_code_safety
import pandas as pd
import numpy as np


def test_library_modification():
    """测试库修改攻击"""
    
    print("\n" + "="*60)
    print("测试：修改共享库的行为")
    print("="*60)
    
    # 保存原始的 pandas.DataFrame
    original_dataframe = pd.DataFrame
    
    # 测试代码：尝试修改 pandas.DataFrame
    malicious_code = """
# 尝试修改 pandas.DataFrame 的行为
import pandas as pd

# 保存原始的 __init__
_original_init = pd.DataFrame.__init__

# 创建恶意的 __init__
def malicious_init(self, *args, **kwargs):
    print("🚨 DataFrame 被劫持了！")
    _original_init(self, *args, **kwargs)
    # 可以在这里窃取数据、修改数据等

# 替换 __init__
pd.DataFrame.__init__ = malicious_init

result = "DataFrame modified"
"""
    
    print("恶意代码:")
    print(malicious_code)
    print()
    
    # 1. 静态检查
    is_safe, error_msg = validate_code_safety(malicious_code)
    print(f"[静态检查] {'✓ 通过' if is_safe else '✗ 拦截'}")
    if not is_safe:
        print(f"  原因: {error_msg}")
    print()
    
    # 2. 执行恶意代码
    exec_globals = {
        'pd': pd,
        'np': np,
    }
    
    result = safe_exec_code(
        code=malicious_code,
        exec_globals=exec_globals,
        timeout=5
    )
    
    print(f"[运行时] {'✓ 执行成功' if result['success'] else '✗ 执行失败'}")
    if not result['success']:
        print(f"  错误: {result['error'][:200]}")
    print()
    
    # 3. 验证库是否被修改
    print("[验证] 检查 pandas.DataFrame 是否被修改...")
    
    # 创建一个新的 DataFrame 看是否触发恶意代码
    try:
        test_df = pd.DataFrame({'a': [1, 2, 3]})
        print("  创建 DataFrame 成功")
        
        # 检查 __init__ 是否被修改
        if pd.DataFrame.__init__ != original_dataframe.__init__:
            print("  ✗✗✗ 严重安全漏洞！pandas.DataFrame 已被修改！")
            print("  这意味着恶意代码可以影响同一进程中的其他策略！")
        else:
            print("  ✓ pandas.DataFrame 未被修改")
    except Exception as e:
        print(f"  创建 DataFrame 失败: {e}")
    
    print()
    
    # 4. 测试其他修改方式
    print("[测试] 其他库修改方式...")
    
    test_cases = [
        ("修改 numpy 函数", """
import numpy as np
_original_mean = np.mean
np.mean = lambda x: 999999  # 总是返回错误值
result = "numpy.mean modified"
"""),
        ("修改 pandas 方法", """
import pandas as pd
_original_rolling = pd.Series.rolling
pd.Series.rolling = lambda self, *args, **kwargs: self  # 破坏 rolling
result = "Series.rolling modified"
"""),
        ("添加恶意属性", """
import pandas as pd
pd._malicious_flag = True
pd._steal_data = lambda df: print("Stealing:", df.head())
result = "malicious attributes added"
"""),
        ("修改全局变量", """
# 尝试修改传入的 df
if 'df' in dir():
    df._is_compromised = True
result = "global df modified"
"""),
    ]
    
    for name, code in test_cases:
        print(f"\n  测试: {name}")
        is_safe, _ = validate_code_safety(code)
        exec_result = safe_exec_code(code, {'pd': pd, 'np': np}, timeout=5)
        
        if exec_result['success']:
            print(f"    ✗ 代码执行成功（可能存在风险）")
        else:
            print(f"    ✓ 代码被阻止")
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


def test_monkey_patching():
    """测试猴子补丁攻击"""
    
    print("\n" + "="*60)
    print("测试：猴子补丁（Monkey Patching）攻击")
    print("="*60)
    
    code = """
# 猴子补丁：修改内置函数的行为
import pandas as pd

# 劫持 DataFrame.mean() 方法
original_mean = pd.DataFrame.mean

def evil_mean(self, *args, **kwargs):
    # 在计算均值时偷偷修改数据
    print("🚨 正在窃取数据...")
    result = original_mean(self, *args, **kwargs)
    # 返回错误的结果
    return result * 1.1  # 所有均值都增加 10%

pd.DataFrame.mean = evil_mean

# 测试
test_df = pd.DataFrame({'price': [100, 200, 300]})
result = test_df.mean()
print(f"被篡改的均值: {result}")
"""
    
    print("代码:")
    print(code)
    print()
    
    is_safe, error_msg = validate_code_safety(code)
    print(f"[静态检查] {'✓ 通过' if is_safe else '✗ 拦截'}")
    if not is_safe:
        print(f"  原因: {error_msg}")
    
    exec_result = safe_exec_code(code, {'pd': pd, 'np': np}, timeout=5)
    print(f"[运行时] {'✓ 执行成功' if exec_result['success'] else '✗ 执行失败'}")
    
    if exec_result['success']:
        print("  ✗✗✗ 猴子补丁攻击成功！")
    
    print()


def test_state_pollution():
    """测试状态污染攻击"""
    
    print("\n" + "="*60)
    print("测试：状态污染（State Pollution）")
    print("="*60)
    
    print("场景：两个策略在同一进程中执行")
    print()
    
    # 策略1：恶意策略
    strategy1 = """
import pandas as pd
import numpy as np

# 恶意策略：修改 numpy 的随机种子和全局状态
np.random.seed(12345)  # 固定随机种子
pd.set_option('mode.chained_assignment', None)  # 关闭警告

# 修改 numpy 的默认行为
np.set_printoptions(threshold=10)

# 在 pandas 中注入恶意数据
if not hasattr(pd, '_evil_cache'):
    pd._evil_cache = {}
pd._evil_cache['stolen_data'] = "sensitive information"

result = "Strategy 1 executed"
"""
    
    # 策略2：正常策略
    strategy2 = """
import pandas as pd
import numpy as np

# 正常策略：期望干净的环境
random_value = np.random.random()  # 期望真随机，但可能被固定了

# 检查是否有恶意缓存
if hasattr(pd, '_evil_cache'):
    print(f"🚨 发现恶意缓存: {pd._evil_cache}")
    result = "Environment is polluted!"
else:
    result = "Environment is clean"
"""
    
    print("策略1（恶意）:")
    print(strategy1)
    print()
    
    # 执行策略1
    result1 = safe_exec_code(strategy1, {'pd': pd, 'np': np}, timeout=5)
    print(f"策略1执行: {'成功' if result1['success'] else '失败'}")
    print()
    
    print("策略2（正常）:")
    print(strategy2)
    print()
    
    # 执行策略2
    result2 = safe_exec_code(strategy2, {'pd': pd, 'np': np}, timeout=5)
    print(f"策略2执行: {'成功' if result2['success'] else '失败'}")
    
    # 检查状态是否被污染
    if hasattr(pd, '_evil_cache'):
        print("\n✗✗✗ 状态污染攻击成功！")
        print(f"  恶意缓存内容: {pd._evil_cache}")
        # 清理
        delattr(pd, '_evil_cache')
    else:
        print("\n✓ 环境未被污染")
    
    print()


if __name__ == '__main__':
    test_library_modification()
    test_monkey_patching()
    test_state_pollution()
    
    print("\n" + "="*60)
    print("总结")
    print("="*60)
    print("""
如果以上测试中有任何 ✗✗✗ 标记，说明存在严重的安全问题：

1. 库修改攻击：恶意代码可以修改 pandas/numpy 的行为
2. 猴子补丁：可以劫持方法，窃取或篡改数据
3. 状态污染：一个策略可以影响其他策略的执行环境

建议的解决方案：
1. 使用独立进程执行每个策略（multiprocessing）
2. 使用 Docker 容器完全隔离
3. 使用 RestrictedPython 等成熟的沙箱库
4. 在每次执行前重新导入库（性能较差）
5. 使用 copy-on-write 机制保护共享对象
""")
