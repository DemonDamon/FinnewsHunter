import __init__

from Kite import config

from Killua.denull import DeNull
from Killua.deduplication import Deduplication
from Killua.buildstocknewsdb import GenStockNewsDB

from Gon.jrjspyder import JrjSpyder


# 1. 爬取历史数据
jrj_spyder = JrjSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
jrj_spyder.get_historical_news(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ, start_date="2015-01-01")

# 2. 针对历史数据进行去重清洗
Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()

# 3. 将历史数据中包含null值的行去掉
DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()

# 4. 创建新的数据库，针对每一个股票，将所有涉及该股票的新闻都保存在新的数据库，并贴好"利好","利空"和"中性"标签
gen_stock_news_db = GenStockNewsDB()
gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
