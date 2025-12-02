import __init__

import json
import redis
import logging
import datetime
import akshare as ak

from Kite import config
from Kite.database import Database

from Leorio.tokenization import Tokenization
from Leorio.topicmodelling import TopicModelling

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class GenStockNewsDB(object):

    def __init__(self):
        self.database = Database()
        # 获取从1990-12-19至2020-12-31股票交易日数据
        self.trade_date = ak.tool_trade_date_hist_sina()["trade_date"].tolist()
        self.label_range = {3: "3DaysLabel",
                            5: "5DaysLabel",
                            10: "10DaysLabel",
                            15: "15DaysLabel",
                            30: "30DaysLabel",
                            60: "60DaysLabel"}
        self.redis_client = redis.StrictRedis(host=config.REDIS_IP,
                                              port=config.REDIS_PORT,
                                              db=config.CACHE_NEWS_REDIS_DB_ID)
        self.redis_client.set("today_date", datetime.datetime.now().strftime("%Y-%m-%d"))
        self.redis_client.delete("stock_news_num_over_{}".format(config.MINIMUM_STOCK_NEWS_NUM_FOR_ML))
        self._stock_news_nums_stat()

    def get_all_news_about_specific_stock(self, database_name, collection_name):
        # 获取collection_name的key值，看是否包含RelatedStockCodes，如果没有说明，没有做将新闻中所涉及的
        # 股票代码保存在新的一列
        _keys_list = list(next(self.database.get_collection(database_name, collection_name).find()).keys())
        if "RelatedStockCodes" not in _keys_list:
            tokenization = Tokenization(import_module="jieba", user_dict="./Leorio/financedict.txt")
            tokenization.update_news_database_rows(database_name, collection_name)
        # 创建stock_code为名称的collection
        stock_symbol_list = self.database.get_data(config.STOCK_DATABASE_NAME,
                                                   config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                                   keys=["symbol"])["symbol"].to_list()
        col_names = self.database.connect_database(config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE).list_collection_names(session=None)
        for symbol in stock_symbol_list:
            if symbol not in col_names:
                # if int(symbol[2:]) > 837:
                _collection = self.database.get_collection(config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE, symbol)
                _tmp_num_stat = 0
                for row in self.database.get_collection(database_name, collection_name).find():  # 迭代器
                    if symbol[2:] in row["RelatedStockCodes"].split(" "):
                        # 返回新闻发布后n天的标签
                        _tmp_dict = {}
                        for label_days, key_name in self.label_range.items():
                            _tmp_res = self._label_news(
                                datetime.datetime.strptime(row["Date"].split(" ")[0], "%Y-%m-%d"), symbol, label_days)
                            _tmp_dict.update({key_name: _tmp_res})
                        _data = {"Date": row["Date"],
                                 "Url": row["Url"],
                                 "Title": row["Title"],
                                 "Article": row["Article"],
                                 "OriDB": database_name,
                                 "OriCOL": collection_name}
                        _data.update(_tmp_dict)
                        _collection.insert_one(_data)
                        _tmp_num_stat += 1
                logging.info("there are {} news mentioned {} in {} collection need to be fetched ... "
                             .format(_tmp_num_stat, symbol, collection_name))
            # else:
            #     logging.info("{} has fetched all related news from {}...".format(symbol, collection_name))

    def listen_redis_queue(self):
        # 监听redis消息队列，当新的实时数据过来时，根据"RelatedStockCodes"字段，将新闻分别保存到对应的股票数据库
        # e.g.:缓存新的一条数据中，"RelatedStockCodes"字段数据为"603386 603003 600111 603568"，则将该条新闻分别
        # 都存进这四支股票对应的数据库中
        crawled_url_today = set()
        while True:
            date_now = datetime.datetime.now().strftime("%Y-%m-%d")
            if date_now != self.redis_client.get("today_date").decode():
                crawled_url_today = set()
                self.redis_client.set("today_date", date_now)
            if self.redis_client.llen(config.CACHE_NEWS_LIST_NAME) != 0:
                data = json.loads(self.redis_client.lindex(config.CACHE_NEWS_LIST_NAME, -1))
                if data["Url"] not in crawled_url_today:  # 排除重复插入冗余文本
                    crawled_url_today.update({data["Url"]})
                    if data["RelatedStockCodes"] != "":
                        for stock_code in data["RelatedStockCodes"].split(" "):
                            # 将新闻分别送进相关股票数据库
                            symbol = "sh{}".format(stock_code) if stock_code[0] == "6" else "sz{}".format(stock_code)
                            _collection = self.database.get_collection(config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE, symbol)
                            _tmp_dict = {}
                            for label_days, key_name in self.label_range.items():
                                _tmp_res = self._label_news(
                                    datetime.datetime.strptime(data["Date"].split(" ")[0], "%Y-%m-%d"), symbol, label_days)
                                _tmp_dict.update({key_name: _tmp_res})
                            _data = {"Date": data["Date"],
                                     "Url": data["Url"],
                                     "Title": data["Title"],
                                     "Article": data["Article"],
                                     "OriDB": data["OriDB"],
                                     "OriCOL": data["OriCOL"]}
                            _data.update(_tmp_dict)
                            _collection.insert_one(_data)
                            logging.info("the real-time fetched news {}, which was saved in [DB:{} - COL:{}] ...".format(data["Title"],
                                                                                                                         config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE,
                                                                                                                         symbol))
                            #
                            # if symbol.encode() in self.redis_client.lrange("stock_news_num_over_{}".format(config.MINIMUM_STOCK_NEWS_NUM_FOR_ML), 0, -1):
                            #     label_name = "3DaysLabel"
                            #     # classifier_save_path = "{}_classifier.pkl".format(symbol)
                            #     ori_dict_path = "{}_docs_dict.dict".format(symbol)
                            #     bowvec_save_path = "{}_bowvec.mm".format(symbol)
                            #
                            #     topicmodelling = TopicModelling()
                            #     chn_label = topicmodelling.classify_stock_news(data["Article"],
                            #                                                    config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE,
                            #                                                    symbol,
                            #                                                    label_name=label_name,
                            #                                                    topic_model_type="lsi",
                            #                                                    classifier_model="rdforest",  # rdforest / svm
                            #                                                    ori_dict_path=ori_dict_path,
                            #                                                    bowvec_save_path=bowvec_save_path)
                            #     logging.info(
                            #         "document '{}...' was classified with label '{}' for symbol {} ... ".format(
                            #             data["Article"][:20], chn_label, symbol))

                    self.redis_client.rpop(config.CACHE_NEWS_LIST_NAME)
                    logging.info("now pop {} from redis queue of [DB:{} - KEY:{}] ... ".format(data["Title"],
                                                                                               config.CACHE_NEWS_REDIS_DB_ID,
                                                                                               config.CACHE_NEWS_LIST_NAME))

    def _label_news(self, date, symbol, n_days):
        """
        :param date: 类型datetime.datetime，表示新闻发布的日期，只包括年月日，不包括具体时刻，如datetime.datetime(2015, 1, 5, 0, 0)
        :param symbol: 类型str，表示股票标的，如sh600000
        :param n_days: 类型int，表示根据多少天后的价格设定标签，如新闻发布后n_days天，如果收盘价格上涨，则认为该则新闻是利好消息
        """
        # 计算新闻发布当天经过n_days天后的具体年月日
        this_date_data = self.database.get_data(config.STOCK_DATABASE_NAME,
                                                symbol,
                                                query={"date": date})
        # 考虑情况：新闻发布日期是非交易日，因此该日期没有价格数据，则往前寻找，比如新闻发布日期是2020-12-12是星期六，
        # 则考虑2020-12-11日的收盘价作为该新闻发布时的数据
        tmp_date = date
        if this_date_data is None:
            i = 1
            while this_date_data is None and i <= 10:
                tmp_date -= datetime.timedelta(days=i)
                # 判断日期是否是交易日，如果是再去查询数据库；如果this_date_data还是NULL值，则说明数据库没有该交易日数据
                if tmp_date.strftime("%Y-%m-%d") in self.trade_date:
                    this_date_data = self.database.get_data(config.STOCK_DATABASE_NAME,
                                                            symbol,
                                                            query={"date": tmp_date})
                i += 1
        try:
            close_price_this_date = this_date_data["close"][0]
        except Exception:
            close_price_this_date = None
        # 考虑情况：新闻发布后n_days天是非交易日，或者没有采集到数据，因此向后寻找，如新闻发布日期是2020-12-08，5天
        # 后的日期是2020-12-13是周日，因此将2020-12-14日周一的收盘价作为n_days后的数据
        new_date = date + datetime.timedelta(days=n_days)
        n_days_later_data = self.database.get_data(config.STOCK_DATABASE_NAME,
                                                   symbol,
                                                   query={"date": new_date})
        if n_days_later_data is None:
            i = 1
            while n_days_later_data is None and i <= 10:
                new_date = date + datetime.timedelta(days=n_days+i)
                if new_date.strftime("%Y-%m-%d") in self.trade_date:
                    n_days_later_data = self.database.get_data(config.STOCK_DATABASE_NAME,
                                                               symbol,
                                                               query={"date": new_date})
                i += 1
        try:
            close_price_n_days_later = n_days_later_data["close"][0]
        except Exception:
            close_price_n_days_later = None
        # 判断条件：
        # （1）如果n_days个交易日后且n_days<=10天，则价格上涨(下跌)超过3%，则认为该新闻是利好(利空)消息；如果价格在3%的范围内，则为中性消息
        # （2）如果n_days个交易日后且10<n_days<=15天，则价格上涨(下跌)超过5%，则认为该新闻是利好(利空)消息；如果价格在5%的范围内，则为中性消息
        # （3）如果n_days个交易日后且15<n_days<=30天，则价格上涨(下跌)超过10%，则认为该新闻是利好(利空)消息；如果价格在10%的范围内，则为中性消息
        # （4）如果n_days个交易日后且30<n_days<=60天，则价格上涨(下跌)超过15%，则认为该新闻是利好(利空)消息；如果价格在15%的范围内，则为中性消息
        # Note：中性消息定义为，该消息迅速被市场消化，并没有持续性影响
        param = 0.01
        if n_days <= 10:
            param = 0.03
        elif 10 < n_days <= 15:
            param = 0.05
        elif 15 < n_days <= 30:
            param = 0.10
        elif 30 < n_days <= 60:
            param = 0.15
        if close_price_this_date is not None and close_price_n_days_later is not None:
            if (close_price_n_days_later - close_price_this_date) / close_price_this_date > param:
                return "利好"
            elif (close_price_n_days_later - close_price_this_date) / close_price_this_date < -param:
                return "利空"
            else:
                return "中性"
        else:
            return ""

    def _stock_news_nums_stat(self):
        cols_list = self.database.connect_database(config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE).list_collection_names(session=None)
        for sym in cols_list:
            if self.database.get_collection(config.ALL_NEWS_OF_SPECIFIC_STOCK_DATABASE, sym).estimated_document_count() > config.MINIMUM_STOCK_NEWS_NUM_FOR_ML:
                self.redis_client.lpush("stock_news_num_over_{}".format(config.MINIMUM_STOCK_NEWS_NUM_FOR_ML), sym)


if __name__ == "__main__":
    from Kite import config
    from Killua.buildstocknewsdb import GenStockNewsDB

    gen_stock_news_db = GenStockNewsDB()
    # gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
    # gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
    # gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)

    # gen_stock_news_db.listen_redis_queue()
