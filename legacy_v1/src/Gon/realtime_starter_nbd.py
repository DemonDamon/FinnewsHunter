import __init__

import redis

from Kite import config

from Killua.denull import DeNull
from Killua.deduplication import Deduplication 

from Gon.nbdspyder import NbdSpyder


redis_client = redis.StrictRedis(config.REDIS_IP,
                                 port=config.REDIS_PORT,
                                 db=config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_DB_ID)
redis_client.lpush(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR, "realtime_starter_nbd.py")

# 如果没有历史数据从头爬取，如果已爬取历史数据，则从最新的时间开始爬取
# 如历史数据中最近的新闻时间是"2020-12-09 20:37:10"，则从该时间开始爬取
nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
nbd_spyder.get_historical_news()

# Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
# DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()

nbd_spyder.get_realtime_news()