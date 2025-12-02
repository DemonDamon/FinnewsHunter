import __init__

from Kite import config

from Gon.stockinfospyder import StockInfoSpyder


stock_info_spyder = StockInfoSpyder(config.STOCK_DATABASE_NAME, config.COLLECTION_NAME_STOCK_BASIC_INFO)

# 指定时间段，获取历史数据，如：stock_info_spyder.get_historical_news(start_date="20150101", end_date="20201204")
# 如果没有指定时间段，且数据库已存在部分数据，则从最新的数据时间开始获取直到现在，比如数据库里已有sh600000价格数据到
# 2020-12-03号，如不设定具体时间，则从自动获取sh600000自2020-12-04至当前的价格数据
stock_info_spyder.get_historical_news()
