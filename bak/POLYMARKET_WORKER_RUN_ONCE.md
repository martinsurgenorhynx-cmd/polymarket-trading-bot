# Polymarket Worker - run_once() 方法说明

## 📍 新增功能

在 `PolymarketWorker` 类中添加了 `run_once()` 方法，用于单次执行市场数据更新和AI分析，无需启动后台线程。

---

## 🎯 方法签名

```python
def run_once(
    self, 
    categories: List[str] = None, 
    limit: int = 50, 
    max_analyze: int = 30
) -> Dict:
    """
    单次执行更新和分析（不启动后台线程）
    
    Args:
        categories: 要分析的分类列表，None表示使用默认分类
        limit: 每个分类获取的市场数量
        max_analyze: 最多分析的市场数量
        
    Returns:
        执行结果字典，包含统计信息
    """
```

---

## 📊 返回值

返回一个字典，包含以下字段：

```python
{
    "success": bool,              # 是否执行成功
    "total_markets": int,         # 获取的市场总数
    "unique_markets": int,        # 去重后的市场数
    "rule_filtered": int,         # 规则筛选出的高价值机会数
    "analyzed": int,              # AI分析完成的市场数
    "saved": int,                 # 保存到数据库的结果数
    "elapsed_seconds": float,     # 执行耗时（秒）
    "error": str or None          # 错误信息（如果失败）
}
```

---

## 💡 使用示例

### 示例1: 基本使用

```python
from app.services.polymarket_worker import PolymarketWorker

# 创建worker实例
worker = PolymarketWorker()

# 单次执行（使用默认配置）
result = worker.run_once()

# 检查结果
if result['success']:
    print(f"成功分析 {result['analyzed']} 个市场")
    print(f"耗时 {result['elapsed_seconds']:.1f} 秒")
else:
    print(f"执行失败: {result['error']}")
```

### 示例2: 自定义配置

```python
# 只分析加密货币市场
result = worker.run_once(
    categories=['crypto'],
    limit=20,
    max_analyze=5
)
```

### 示例3: 多个分类

```python
# 分析加密货币和政治市场
result = worker.run_once(
    categories=['crypto', 'politics'],
    limit=30,
    max_analyze=10
)
```

---

## 🧪 测试脚本

`test_polymarket_worker.py` 已更新为使用 `run_once()` 方法：

```bash
# 运行测试
python test_polymarket_worker.py
```

**测试流程**:
1. 导入模块测试
2. 数据源创建测试
3. 获取市场数据测试
4. 规则筛选测试
5. Worker初始化测试
6. **单次执行完整流程测试** ← 新增

---

## 📈 测试结果

### 成功示例

```
================================================================================
测试6: 单次执行完整流程
================================================================================

配置:
  分类: crypto
  每分类市场数: 10
  最多分析: 3

开始执行...

================================================================================
执行结果
================================================================================

✓ 执行成功

统计信息:
  获取市场总数: 10
  去重后市场数: 10
  规则筛选出: 10 个高价值机会
  AI分析完成: 1 个市场
  保存到数据库: 1 个结果
  执行耗时: 112.0 秒

✓ 完整流程测试通过！
  - 成功获取市场数据
  - 成功进行规则筛选
  - 成功完成AI分析
  - 成功保存分析结果
```

---

## 🔄 与其他方法的对比

| 方法 | 用途 | 是否启动线程 | 是否阻塞 |
|------|------|-------------|---------|
| `start()` | 启动后台服务 | ✅ 是 | ❌ 否 |
| `force_update()` | 强制更新（需先start） | ❌ 否 | ✅ 是 |
| `run_once()` | 单次执行 | ❌ 否 | ✅ 是 |

### 使用场景

**`start()` - 后台服务模式**
```python
worker = PolymarketWorker()
worker.start()  # 启动后台线程，定期自动更新
# 主程序继续运行...
```

**`force_update()` - 手动触发更新**
```python
worker = PolymarketWorker()
worker.start()  # 必须先启动
# ... 一段时间后 ...
worker.force_update()  # 立即执行一次更新
```

**`run_once()` - 单次执行**
```python
worker = PolymarketWorker()
result = worker.run_once()  # 执行一次后退出
# 不需要start()，执行完成后自动退出
```

---

## 🎯 适用场景

### 1. 测试和调试

```python
# 快速测试功能是否正常
worker = PolymarketWorker()
result = worker.run_once(
    categories=['crypto'],
    limit=5,
    max_analyze=2
)
```

### 2. 定时任务（Cron）

```bash
# 每天凌晨2点执行一次
0 2 * * * cd /path/to/backend && python -c "
from app.services.polymarket_worker import PolymarketWorker
worker = PolymarketWorker()
worker.run_once()
"
```

### 3. 手动触发

```python
# 在API端点中手动触发
@app.route('/api/polymarket/update', methods=['POST'])
def trigger_update():
    worker = PolymarketWorker()
    result = worker.run_once()
    return jsonify(result)
```

### 4. 脚本化执行

```python
# 批量处理不同配置
configs = [
    {'categories': ['crypto'], 'max_analyze': 10},
    {'categories': ['politics'], 'max_analyze': 5},
    {'categories': ['sports'], 'max_analyze': 3},
]

worker = PolymarketWorker()
for config in configs:
    result = worker.run_once(**config)
    print(f"Processed {config['categories']}: {result['analyzed']} analyzed")
```

---

## ⚡ 性能特点

### 优点

1. **无线程开销** - 不创建后台线程
2. **可控执行** - 明确的开始和结束
3. **易于调试** - 同步执行，便于追踪
4. **资源友好** - 执行完成后立即释放资源

### 注意事项

1. **阻塞执行** - 会阻塞当前线程直到完成
2. **无自动重试** - 失败后不会自动重试
3. **无定时功能** - 需要外部调度（如cron）

---

## 🔧 配置建议

### 快速测试

```python
result = worker.run_once(
    categories=['crypto'],
    limit=5,
    max_analyze=2
)
# 耗时: ~30-60秒
```

### 标准配置

```python
result = worker.run_once(
    categories=['crypto', 'politics'],
    limit=30,
    max_analyze=10
)
# 耗时: ~2-5分钟
```

### 完整分析

```python
result = worker.run_once(
    categories=None,  # 所有分类
    limit=50,
    max_analyze=30
)
# 耗时: ~5-10分钟
```

---

## 📊 错误处理

### 检查执行结果

```python
result = worker.run_once()

if result['success']:
    # 成功
    print(f"分析了 {result['analyzed']} 个市场")
else:
    # 失败
    print(f"错误: {result['error']}")
    # 可以根据错误类型进行重试或告警
```

### 常见错误

| 错误类型 | 原因 | 解决方法 |
|---------|------|---------|
| 网络错误 | 无法连接Polymarket API | 检查网络，配置代理 |
| API错误 | LLM API调用失败 | 检查API密钥和配额 |
| 数据库错误 | 无法保存结果 | 检查数据库连接 |

---

## 🎓 最佳实践

### 1. 先测试后部署

```python
# 1. 小规模测试
result = worker.run_once(categories=['crypto'], limit=5, max_analyze=2)
if not result['success']:
    print(f"测试失败: {result['error']}")
    exit(1)

# 2. 中等规模测试
result = worker.run_once(categories=['crypto'], limit=20, max_analyze=5)

# 3. 完整部署
result = worker.run_once()
```

### 2. 记录执行日志

```python
import logging

result = worker.run_once()
logging.info(f"Polymarket update: {result}")

if result['success']:
    logging.info(f"Analyzed {result['analyzed']} markets in {result['elapsed_seconds']:.1f}s")
else:
    logging.error(f"Update failed: {result['error']}")
```

### 3. 监控和告警

```python
result = worker.run_once()

# 检查是否有足够的分析结果
if result['success'] and result['analyzed'] < 5:
    send_alert("Polymarket分析结果过少，可能存在问题")

# 检查执行时间
if result['elapsed_seconds'] > 600:  # 超过10分钟
    send_alert("Polymarket分析耗时过长")
```

---

## 📚 相关文档

- `POLYMARKET_WORKER_GUIDE.md` - 完整使用指南
- `test_polymarket_worker.py` - 测试脚本
- `app/services/polymarket_worker.py` - 源代码

---

**文档版本**: 1.0  
**最后更新**: 2026-03-06  
**状态**: ✅ 测试通过，可用于生产
