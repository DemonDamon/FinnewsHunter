import __init__

import time
import logging

from Kite import config

from Killua.denull import DeNull
from Killua.deduplication import Deduplication
from Killua.buildstocknewsdb import GenStockNewsDB

from Gon.cnstockspyder import CnStockSpyder


# 1. 爬取历史数据
cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
    logging.info("start crawling {} ...".format(url_to_be_crawled))
    cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn)
    logging.info("finished ...")
    time.sleep(30)

# 2. 针对历史数据进行去重清洗
Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()

# 3. 将历史数据中包含null值的行去掉
DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()

# 4. 创建新的数据库，针对每一个股票，将所有涉及该股票的新闻都保存在新的数据库，并贴好"利好","利空"和"中性"标签
gen_stock_news_db = GenStockNewsDB()
gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)

