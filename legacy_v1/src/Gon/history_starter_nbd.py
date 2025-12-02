import __init__

from Kite import config

from Killua.denull import DeNull
from Killua.deduplication import Deduplication
from Killua.buildstocknewsdb import GenStockNewsDB

from Gon.nbdspyder import NbdSpyder


# 1. 爬取历史数据
nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
nbd_spyder.get_historical_news(start_page=684)

# 2. 针对历史数据进行去重清洗
Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()

# 3. 将历史数据中包含null值的行去掉
DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()

# 4. 创建新的数据库，针对每一个股票，将所有涉及该股票的新闻都保存在新的数据库，并贴好"利好","利空"和"中性"标签
gen_stock_news_db = GenStockNewsDB()
gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
