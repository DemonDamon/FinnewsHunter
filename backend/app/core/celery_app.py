"""
Celery 应用配置
"""
from celery import Celery
from celery.schedules import crontab
from .config import settings

# 创建 Celery 应用
celery_app = Celery(
    "finnews",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.crawl_tasks"]  # 导入任务模块
)

# Celery 配置
celery_app.conf.update(
    # 时区设置
    timezone="Asia/Shanghai",
    enable_utc=True,
    
    # 任务结果配置
    result_expires=3600,  # 结果保存1小时
    result_backend_transport_options={
        'master_name': 'mymaster'
    },
    
    # 任务执行配置
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=30 * 60,  # 30分钟超时
    task_soft_time_limit=25 * 60,  # 25分钟软超时
    
    # Worker 配置
    worker_prefetch_multiplier=1,  # 每次只拿一个任务
    worker_max_tasks_per_child=1000,  # 每个 worker 处理1000个任务后重启
    
    # Beat 调度配置
    beat_schedule={
        # 每5分钟爬取新浪财经
        "crawl-sina-every-5min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/5"),  # 每5分钟
            "args": ("sina",),
        },
        # 可以添加更多定时任务
        # "crawl-jrj-every-15min": {
        #     "task": "app.tasks.crawl_tasks.realtime_crawl_task",
        #     "schedule": crontab(minute="*/15"),
        #     "args": ("jrj",),
        # },
    },
)

# 任务路由（可选，用于任务分发）
# 注释掉自定义路由，使用默认的 celery 队列
# celery_app.conf.task_routes = {
#     "app.tasks.crawl_tasks.*": {"queue": "crawl"},
#     "app.tasks.analysis_tasks.*": {"queue": "analysis"},
# }


if __name__ == "__main__":
    celery_app.start()

