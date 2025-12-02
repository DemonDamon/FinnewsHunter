import __init__

import redis

from Kite import config

from Killua.buildstocknewsdb import GenStockNewsDB


redis_client = redis.StrictRedis(config.REDIS_IP,
                                 port=config.REDIS_PORT,
                                 db=config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_DB_ID)
redis_client.lpush(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR, "realtime_starter_redis_queue.py")

gen_stock_news_db = GenStockNewsDB()
gen_stock_news_db.listen_redis_queue()