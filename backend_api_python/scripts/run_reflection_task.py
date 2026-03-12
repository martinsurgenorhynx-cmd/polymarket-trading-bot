import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from app.services.agents.reflection import ReflectionService

def main():
    """
    运行自动反思验证任务
    建议通过 cron 或 定时任务调度器 每天运行一次
    """
    print("Running Automated Reflection Verification Task...")
    service = ReflectionService()
    service.run_verification_cycle()
    print("Task Completed.")

if __name__ == "__main__":
    main()

