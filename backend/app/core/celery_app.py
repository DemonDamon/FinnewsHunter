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
        # 每1分钟爬取新浪财经
        "crawl-sina-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("sina",),
        },
        # 每1分钟爬取腾讯财经
        "crawl-tencent-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("tencent",),
        },
        # 每1分钟爬取中新经纬
        "crawl-jwview-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("jwview",),
        },
        # 每1分钟爬取经济观察网
        "crawl-eeo-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("eeo",),
        },
        # 每1分钟爬取财经网
        "crawl-caijing-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("caijing",),
        },
        # 每1分钟爬取21经济网
        "crawl-jingji21-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("jingji21",),
        },
        # 每1分钟爬取每日经济新闻
        "crawl-nbd-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("nbd",),
        },
        # 每1分钟爬取第一财经
        "crawl-yicai-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("yicai",),
        },
        # 每1分钟爬取网易财经
        "crawl-163-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("163",),
        },
        # 每1分钟爬取东方财富
        "crawl-eastmoney-every-1min": {
            "task": "app.tasks.crawl_tasks.realtime_crawl_task",
            "schedule": crontab(minute="*/1"),
            "args": ("eastmoney",),
        },
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

