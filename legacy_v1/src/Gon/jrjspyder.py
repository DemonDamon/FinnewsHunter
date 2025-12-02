"""
金融界：http://www.jrj.com.cn
股票频道全部新闻：http://stock.jrj.com.cn/xwk/202012/20201203_1.shtml
"""

import __init__

from spyder import Spyder

from Kite import utils
from Kite import config
from Kite.database import Database

from Leorio.tokenization import Tokenization

import time
import json
import redis
import datetime
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class JrjSpyder(Spyder):

    def __init__(self, database_name, collection_name):
        super(JrjSpyder, self).__init__()
        self.db_obj = Database()
        self.col = self.db_obj.conn[database_name].get_collection(collection_name)
        self.terminated_amount = 0
        self.db_name = database_name
        self.col_name = collection_name
        self.tokenization = Tokenization(import_module="jieba", user_dict=config.USER_DEFINED_DICT_PATH)
        self.redis_client = redis.StrictRedis(host=config.REDIS_IP,
                                              port=config.REDIS_PORT,
                                              db=config.CACHE_NEWS_REDIS_DB_ID)

    def get_url_info(self, url, specific_date):
        try:
            bs = utils.html_parser(url)
        except Exception:
            return False
        date = ""
        for span in bs.find_all("span"):
            if span.contents[0] == "jrj_final_date_start":
                date = span.text.replace("\r", "").replace("\n", "")
                break
        if date == "":
            date = specific_date
        article = ""
        for p in bs.find_all("p"):
            if not p.find_all("jrj_final_daohang_start") and p.attrs == {} and \
                    not p.find_all("input") and not p.find_all("a", attrs={"class": "red"}) and not p.find_all("i") and not p.find_all("span"):
                # if p.contents[0] != "jrj_final_daohang_start1" and p.attrs == {} and \
                #         not p.find_all("input") and not p.find_all("a", attrs={"class": "red"}) and not p.find_all("i"):
                article += p.text.replace("\r", "").replace("\n", "").replace("\u3000", "")

        return [date, article]

    def get_historical_news(self, url, start_date=None, end_date=None):
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)

        crawled_urls_list = []
        if end_date is None:
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")

        if start_date is None:
            # 如果start_date是None，则从历史数据库最新的日期补充爬取到最新日期
            # e.g. history_latest_date_str -> "2020-12-08"
            #      history_latest_date_dt -> datetime.date(2020, 12, 08)
            #      start_date -> "2020-12-09"
            history_latest_date_list = self.db_obj.get_data(self.db_name,
                                                            self.col_name,
                                                            keys=["Date"])["Date"].to_list()
            if len(history_latest_date_list) != 0:
                history_latest_date_str = max(history_latest_date_list).split(" ")[0]
                history_latest_date_dt = datetime.datetime.strptime(history_latest_date_str, "%Y-%m-%d").date()
                offset = datetime.timedelta(days=1)
                start_date = (history_latest_date_dt + offset).strftime('%Y-%m-%d')
            else:
                start_date = config.JRJ_REQUEST_DEFAULT_DATE

        dates_list = utils.get_date_list_from_range(start_date, end_date)
        dates_separated_into_ranges_list = utils.gen_dates_list(dates_list, config.JRJ_DATE_RANGE)

        for dates_range in dates_separated_into_ranges_list:
            for date in dates_range:
                first_url = "{}/{}/{}_1.shtml".format(url, date.replace("-", "")[0:6], date.replace("-", ""))
                max_pages_num = utils.search_max_pages_num(first_url, date)
                for num in range(1, max_pages_num + 1):
                    _url = "{}/{}/{}_{}.shtml".format(url, date.replace("-", "")[0:6], date.replace("-", ""), str(num))
                    bs = utils.html_parser(_url)
                    a_list = bs.find_all("a")
                    for a in a_list:
                        if "href" in a.attrs and a.string and \
                                a["href"].find("/{}/{}/".format(date.replace("-", "")[:4],
                                                                date.replace("-", "")[4:6])) != -1:
                            if a["href"] not in crawled_urls_list:
                                # 如果标题不包含"收盘","报于"等字样，即可写入数据库，因为包含这些字样标题的新闻多为机器自动生成
                                if a.string.find("收盘") == -1 and a.string.find("报于") == -1 and \
                                        a.string.find("新三板挂牌上市") == -1:
                                    result = self.get_url_info(a["href"], date)
                                    while not result:
                                        self.terminated_amount += 1
                                        if self.terminated_amount > config.JRJ_MAX_REJECTED_AMOUNTS:
                                            # 始终无法爬取的URL保存起来
                                            with open(config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                file.write("{}\n".format(a["href"]))
                                            logging.info("rejected by remote server longer than {} minutes, "
                                                         "and the failed url has been written in path {}"
                                                         .format(config.JRJ_MAX_REJECTED_AMOUNTS,
                                                                 config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH))
                                            break
                                        logging.info("rejected by remote server, request {} again after "
                                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                        time.sleep(60 * self.terminated_amount)
                                        result = self.get_url_info(a["href"], date)
                                    if not result:
                                        # 爬取失败的情况
                                        logging.info("[FAILED] {} {}".format(a.string, a["href"]))
                                    else:
                                        # 有返回但是article为null的情况
                                        article_specific_date, article = result
                                        while article == "" and self.is_article_prob >= .1:
                                            self.is_article_prob -= .1
                                            result = self.get_url_info(a["href"], date)
                                            while not result:
                                                self.terminated_amount += 1
                                                if self.terminated_amount > config.JRJ_MAX_REJECTED_AMOUNTS:
                                                    # 始终无法爬取的URL保存起来
                                                    with open(config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                        file.write("{}\n".format(a["href"]))
                                                    logging.info("rejected by remote server longer than {} minutes, "
                                                                 "and the failed url has been written in path {}"
                                                                 .format(config.JRJ_MAX_REJECTED_AMOUNTS,
                                                                         config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH))
                                                    break
                                                logging.info("rejected by remote server, request {} again after "
                                                             "{} seconds...".format(a["href"],
                                                                                    60 * self.terminated_amount))
                                                time.sleep(60 * self.terminated_amount)
                                                result = self.get_url_info(a["href"], date)
                                            article_specific_date, article = result
                                        self.is_article_prob = .5
                                        if article != "":
                                                related_stock_codes_list = self.tokenization.find_relevant_stock_codes_in_article(article,
                                                                                                                                  name_code_dict)
                                                data = {"Date": article_specific_date,
                                                        "Url": a["href"],
                                                        "Title": a.string,
                                                        "Article": article,
                                                        "RelatedStockCodes": " ".join(related_stock_codes_list)}
                                                # self.col.insert_one(data)
                                                self.db_obj.insert_data(self.db_name, self.col_name, data)
                                                logging.info("[SUCCESS] {} {} {}".format(article_specific_date,
                                                                                         a.string,
                                                                                         a["href"]))
                                    self.terminated_amount = 0  # 爬取结束后重置该参数
                                else:
                                    logging.info("[QUIT] {}".format(a.string))

    def get_realtime_news(self, interval=60):
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        # crawled_urls_list = []
        is_change_date = False
        last_date = datetime.datetime.now().strftime("%Y-%m-%d")
        while True:
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            if today_date != last_date:
                is_change_date = True
                last_date = today_date
            if is_change_date:
                # crawled_urls_list = []
                utils.batch_lpop(self.redis_client,
                                 config.CACHE_SAVED_NEWS_JRJ_TODAY_VAR_NAME,
                                 self.redis_client.llen(config.CACHE_SAVED_NEWS_JRJ_TODAY_VAR_NAME))
                is_change_date = False
            _url = "{}/{}/{}_1.shtml".format(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ,
                                             today_date.replace("-", "")[0:6],
                                             today_date.replace("-", ""))
            max_pages_num = utils.search_max_pages_num(_url, today_date)
            for num in range(1, max_pages_num + 1):
                _url = "{}/{}/{}_{}.shtml".format(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ,
                                                  today_date.replace("-", "")[0:6],
                                                  today_date.replace("-", ""),
                                                  str(num))
                bs = utils.html_parser(_url)
                a_list = bs.find_all("a")
                for a in a_list:
                    if "href" in a.attrs and a.string and \
                            a["href"].find("/{}/{}/".format(today_date.replace("-", "")[:4],
                                                            today_date.replace("-", "")[4:6])) != -1:
                        # if a["href"] not in crawled_urls_list:
                        if a["href"] not in self.redis_client.lrange(config.CACHE_SAVED_NEWS_JRJ_TODAY_VAR_NAME, 0, -1):
                            # 如果标题不包含"收盘","报于"等字样，即可写入数据库，因为包含这些字样标题的新闻多为机器自动生成
                            if a.string.find("收盘") == -1 and a.string.find("报于") == -1 and \
                                    a.string.find("新三板挂牌上市") == -1:
                                result = self.get_url_info(a["href"], today_date)
                                while not result:
                                    self.terminated_amount += 1
                                    if self.terminated_amount > config.JRJ_MAX_REJECTED_AMOUNTS:
                                        # 始终无法爬取的URL保存起来
                                        with open(config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                            file.write("{}\n".format(a["href"]))
                                        logging.info("rejected by remote server longer than {} minutes, "
                                                     "and the failed url has been written in path {}"
                                                     .format(config.JRJ_MAX_REJECTED_AMOUNTS,
                                                             config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH))
                                        break
                                    logging.info("rejected by remote server, request {} again after "
                                                 "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                    time.sleep(60 * self.terminated_amount)
                                    result = self.get_url_info(a["href"], today_date)
                                if not result:
                                    # 爬取失败的情况
                                    logging.info("[FAILED] {} {}".format(a.string, a["href"]))
                                else:
                                    # 有返回但是article为null的情况
                                    article_specific_date, article = result
                                    while article == "" and self.is_article_prob >= .1:
                                        self.is_article_prob -= .1
                                        result = self.get_url_info(a["href"], today_date)
                                        while not result:
                                            self.terminated_amount += 1
                                            if self.terminated_amount > config.JRJ_MAX_REJECTED_AMOUNTS:
                                                # 始终无法爬取的URL保存起来
                                                with open(config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                    file.write("{}\n".format(a["href"]))
                                                logging.info("rejected by remote server longer than {} minutes, "
                                                             "and the failed url has been written in path {}"
                                                             .format(config.JRJ_MAX_REJECTED_AMOUNTS,
                                                                     config.RECORD_JRJ_FAILED_URL_TXT_FILE_PATH))
                                                break
                                            logging.info("rejected by remote server, request {} again after "
                                                         "{} seconds...".format(a["href"],
                                                                                60 * self.terminated_amount))
                                            time.sleep(60 * self.terminated_amount)
                                            result = self.get_url_info(a["href"], today_date)
                                        article_specific_date, article = result
                                    self.is_article_prob = .5
                                    if article != "":
                                        related_stock_codes_list = self.tokenization.find_relevant_stock_codes_in_article(article,
                                                                                                                          name_code_dict)
                                        self.db_obj.insert_data(self.db_name, self.col_name,
                                                                {"Date": article_specific_date,
                                                                 "Url": a["href"],
                                                                 "Title": a.string,
                                                                 "Article": article,
                                                                 "RelatedStockCodes": " ".join(related_stock_codes_list)})
                                        self.redis_client.lpush(config.CACHE_NEWS_LIST_NAME, json.dumps(
                                            {"Date": article_specific_date,
                                             "Url": a["href"],
                                             "Title": a.string,
                                             "Article": article,
                                             "RelatedStockCodes": " ".join(related_stock_codes_list),
                                             "OriDB": config.DATABASE_NAME,
                                             "OriCOL": config.COLLECTION_NAME_JRJ
                                             }
                                        ))
                                        logging.info("[SUCCESS] {} {} {}".format(article_specific_date,
                                                                                 a.string,
                                                                                 a["href"]))
                                self.terminated_amount = 0  # 爬取结束后重置该参数
                            else:
                                logging.info("[QUIT] {}".format(a.string))
                            # crawled_urls_list.append(a["href"])
                            self.redis_client.lpush(config.CACHE_SAVED_NEWS_JRJ_TODAY_VAR_NAME, a["href"])
            # logging.info("sleep {} secs then request again ... ".format(interval))
            time.sleep(interval)


# """
# Example-1:
# 爬取历史新闻数据
# """
# if __name__ == "__main__":
#     jrj_spyder = JrjSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
#     jrj_spyder.get_historical_news(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ, start_date="2015-01-01")
#
#     Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()
#     DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()


# """
# Example-2:
# 爬取实时新闻数据
# """
# if __name__ == '__main__':
#     from Kite import config
#     from Gon.jrjspyder import JrjSpyder
#
#     jrj_spyder = JrjSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
#     jrj_spyder.get_historical_news(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ)  # 补充爬虫数据到最新日期
#     jrj_spyder.get_realtime_news()
