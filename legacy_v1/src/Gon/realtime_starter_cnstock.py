import __init__

import time
import redis
import logging
import threading

from Kite import config
from Kite.database import Database

from Killua.denull import DeNull
from Killua.deduplication import Deduplication 

from Gon.cnstockspyder import CnStockSpyder


redis_client = redis.StrictRedis(config.REDIS_IP,
                                 port=config.REDIS_PORT,
                                 db=config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_DB_ID)
redis_client.lpush(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR, "realtime_starter_cnstock.py")

obj = Database()
df = obj.get_data(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK, keys=["Date", "Category"])

cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
# 先补充历史数据，比如已爬取数据到2020-12-01，但是启动实时爬取程序在2020-12-23，则先
# 自动补充爬取2020-12-02至2020-12-23的新闻数据
for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
    # 查询type_chn的最近一条数据的时间
    latets_date_in_db = max(df[df.Category == type_chn]["Date"].to_list())
    cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn, start_date=latets_date_in_db)

Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()

# 开启多线程并行实时爬取
thread_list = []
for url, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
    thread = threading.Thread(target=cnstock_spyder.get_realtime_news, args=(url, type_chn, 60))
    thread_list.append(thread)
for thread in thread_list:
    thread.start()
for thread in thread_list:
    thread.join()