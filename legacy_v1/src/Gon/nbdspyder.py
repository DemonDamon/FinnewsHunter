"""
每经网：http://www.nbd.com.cn
A股动态：http://stocks.nbd.com.cn/columns/275/page/1
"""

import __init__

from spyder import Spyder

from Kite import utils
from Kite import config
from Kite.database import Database

from Leorio.tokenization import Tokenization

import re
import time
import json
import redis
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class NbdSpyder(Spyder):

    def __init__(self, database_name, collection_name):
        super(NbdSpyder, self).__init__()
        self.db_obj = Database()
        self.col = self.db_obj.conn[database_name].get_collection(collection_name)
        self.terminated_amount = 0
        self.db_name = database_name
        self.col_name = collection_name
        self.tokenization = Tokenization(import_module="jieba", user_dict=config.USER_DEFINED_DICT_PATH)
        self.redis_client = redis.StrictRedis(host=config.REDIS_IP,
                                              port=config.REDIS_PORT,
                                              db=config.CACHE_NEWS_REDIS_DB_ID)

    def get_url_info(self, url):
        try:
            bs = utils.html_parser(url)
        except Exception:
            return False
        span_list = bs.find_all("span")
        part = bs.find_all("p")
        article = ""
        date = ""
        for span in span_list:
            if "class" in span.attrs and span.text and span["class"] == ["time"]:
                    string = span.text.split()
                    for dt in string:
                        if dt.find("-") != -1:
                            date += dt + " "
                        elif dt.find(":") != -1:
                            date += dt
                    break
        for paragraph in part:
            chn_status = utils.count_chn(str(paragraph))
            possible = chn_status[1]
            if possible > self.is_article_prob:
                article += str(paragraph)
        while article.find("<") != -1 and article.find(">") != -1:
            string = article[article.find("<"):article.find(">")+1]
            article = article.replace(string, "")
        while article.find("\u3000") != -1:
            article = article.replace("\u3000", "")
        article = " ".join(re.split(" +|\n+", article)).strip()

        return [date, article]

    def get_historical_news(self, start_page=684):
        date_list = self.db_obj.get_data(self.db_name, self.col_name, keys=["Date"])["Date"].to_list()
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        if len(date_list) == 0:
            # 说明没有历史数据，从头开始爬取
            crawled_urls_list = []
            page_urls = ["{}/{}".format(config.WEBSITES_LIST_TO_BE_CRAWLED_NBD, page_id)
                         for page_id in range(start_page, 0, -1)]
            for page_url in page_urls:
                bs = utils.html_parser(page_url)
                a_list = bs.find_all("a")
                for a in a_list:
                    if "click-statistic" in a.attrs and a.string \
                            and a["click-statistic"].find("Article_") != -1 \
                            and a["href"].find("http://www.nbd.com.cn/articles/") != -1:
                        if a["href"] not in crawled_urls_list:
                            result = self.get_url_info(a["href"])
                            while not result:
                                self.terminated_amount += 1
                                if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                    # 始终无法爬取的URL保存起来
                                    with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                        file.write("{}\n".format(a["href"]))
                                    logging.info("rejected by remote server longer than {} minutes, "
                                                 "and the failed url has been written in path {}"
                                                 .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                         config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                    break
                                logging.info("rejected by remote server, request {} again after "
                                             "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                time.sleep(60 * self.terminated_amount)
                                result = self.get_url_info(a["href"])
                            if not result:
                                # 爬取失败的情况
                                logging.info("[FAILED] {} {}".format(a.string, a["href"]))
                            else:
                                # 有返回但是article为null的情况
                                date, article = result
                                while article == "" and self.is_article_prob >= .1:
                                    self.is_article_prob -= .1
                                    result = self.get_url_info(a["href"])
                                    while not result:
                                        self.terminated_amount += 1
                                        if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                            # 始终无法爬取的URL保存起来
                                            with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                file.write("{}\n".format(a["href"]))
                                            logging.info("rejected by remote server longer than {} minutes, "
                                                         "and the failed url has been written in path {}"
                                                         .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                                 config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                            break
                                        logging.info("rejected by remote server, request {} again after "
                                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                        time.sleep(60 * self.terminated_amount)
                                        result = self.get_url_info(a["href"])
                                    date, article = result
                                self.is_article_prob = .5
                                if article != "":
                                    related_stock_codes_list = self.tokenization.find_relevant_stock_codes_in_article(article,
                                                                                                                      name_code_dict)
                                    data = {"Date": date,
                                            # "PageId": page_url.split("/")[-1],
                                            "Url": a["href"],
                                            "Title": a.string,
                                            "Article": article,
                                            "RelatedStockCodes": " ".join(related_stock_codes_list)}
                                    # self.col.insert_one(data)
                                    self.db_obj.insert_data(self.db_name, self.col_name, data)
                                    logging.info("[SUCCESS] {} {} {}".format(date, a.string, a["href"]))
        else:
            is_stop = False
            start_date = max(date_list)
            page_start_id = 1
            while not is_stop:
                page_url = "{}/{}".format(config.WEBSITES_LIST_TO_BE_CRAWLED_NBD, page_start_id)
                bs = utils.html_parser(page_url)
                a_list = bs.find_all("a")
                for a in a_list:
                    if "click-statistic" in a.attrs and a.string \
                            and a["click-statistic"].find("Article_") != -1 \
                            and a["href"].find("http://www.nbd.com.cn/articles/") != -1:
                        result = self.get_url_info(a["href"])
                        while not result:
                            self.terminated_amount += 1
                            if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                # 始终无法爬取的URL保存起来
                                with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                    file.write("{}\n".format(a["href"]))
                                logging.info("rejected by remote server longer than {} minutes, "
                                             "and the failed url has been written in path {}"
                                             .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                     config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                break
                            logging.info("rejected by remote server, request {} again after "
                                         "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                            time.sleep(60 * self.terminated_amount)
                            result = self.get_url_info(a["href"])
                        if not result:
                            # 爬取失败的情况
                            logging.info("[FAILED] {} {}".format(a.string, a["href"]))
                        else:
                            # 有返回但是article为null的情况
                            date, article = result
                            if date > start_date:
                                while article == "" and self.is_article_prob >= .1:
                                    self.is_article_prob -= .1
                                    result = self.get_url_info(a["href"])
                                    while not result:
                                        self.terminated_amount += 1
                                        if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                            # 始终无法爬取的URL保存起来
                                            with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                file.write("{}\n".format(a["href"]))
                                            logging.info("rejected by remote server longer than {} minutes, "
                                                         "and the failed url has been written in path {}"
                                                         .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                                 config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                            break
                                        logging.info("rejected by remote server, request {} again after "
                                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                        time.sleep(60 * self.terminated_amount)
                                        result = self.get_url_info(a["href"])
                                    date, article = result
                                self.is_article_prob = .5
                                if article != "":
                                    related_stock_codes_list = self.tokenization.find_relevant_stock_codes_in_article(article,
                                                                                                                      name_code_dict)
                                    data = {"Date": date,
                                            "Url": a["href"],
                                            "Title": a.string,
                                            "Article": article,
                                            "RelatedStockCodes": " ".join(related_stock_codes_list)}
                                    self.db_obj.insert_data(self.db_name, self.col_name, data)
                                    logging.info("[SUCCESS] {} {} {}".format(date, a.string, a["href"]))
                            else:
                                is_stop = True
                                break
                if not is_stop:
                    page_start_id += 1

    def get_realtime_news(self, interval=60):
        page_url = "{}/1".format(config.WEBSITES_LIST_TO_BE_CRAWLED_NBD)
        logging.info("start real-time crawling of URL -> {}, request every {} secs ... ".format(page_url, interval))
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        # crawled_urls = []
        date_list = self.db_obj.get_data(self.db_name, self.col_name, keys=["Date"])["Date"].to_list()
        latest_date = max(date_list)
        while True:
            # 每隔一定时间轮询该网址
            # if len(crawled_urls) > 100:
            #     # 防止list过长，内存消耗大，维持list在100条
            #     crawled_urls.pop(0)
            if self.redis_client.llen(config.CACHE_SAVED_NEWS_NBD_TODAY_VAR_NAME) > 100:
                # 防止缓存list过长，内存消耗大，维持list在100条
                self.redis_client.rpop(config.CACHE_SAVED_NEWS_NBD_TODAY_VAR_NAME)
            bs = utils.html_parser(page_url)
            a_list = bs.find_all("a")
            for a in a_list:
                if "click-statistic" in a.attrs and a.string \
                        and a["click-statistic"].find("Article_") != -1 \
                        and a["href"].find("http://www.nbd.com.cn/articles/") != -1:
                    # if a["href"] not in crawled_urls:
                    if a["href"] not in self.redis_client.lrange(config.CACHE_SAVED_NEWS_NBD_TODAY_VAR_NAME, 0, -1):
                        result = self.get_url_info(a["href"])
                        while not result:
                            self.terminated_amount += 1
                            if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                # 始终无法爬取的URL保存起来
                                with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                    file.write("{}\n".format(a["href"]))
                                logging.info("rejected by remote server longer than {} minutes, "
                                             "and the failed url has been written in path {}"
                                             .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                     config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                break
                            logging.info("rejected by remote server, request {} again after "
                                         "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                            time.sleep(60 * self.terminated_amount)
                            result = self.get_url_info(a["href"])
                        if not result:
                            # 爬取失败的情况
                            logging.info("[FAILED] {} {}".format(a.string, a["href"]))
                        else:
                            # 有返回但是article为null的情况
                            date, article = result
                            if date > latest_date:
                                while article == "" and self.is_article_prob >= .1:
                                    self.is_article_prob -= .1
                                    result = self.get_url_info(a["href"])
                                    while not result:
                                        self.terminated_amount += 1
                                        if self.terminated_amount > config.NBD_MAX_REJECTED_AMOUNTS:
                                            # 始终无法爬取的URL保存起来
                                            with open(config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                                file.write("{}\n".format(a["href"]))
                                            logging.info("rejected by remote server longer than {} minutes, "
                                                         "and the failed url has been written in path {}"
                                                         .format(config.NBD_MAX_REJECTED_AMOUNTS,
                                                                 config.RECORD_NBD_FAILED_URL_TXT_FILE_PATH))
                                            break
                                        logging.info("rejected by remote server, request {} again after "
                                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                                        time.sleep(60 * self.terminated_amount)
                                        result = self.get_url_info(a["href"])
                                    date, article = result
                                self.is_article_prob = .5
                                if article != "":
                                    related_stock_codes_list = self.tokenization.find_relevant_stock_codes_in_article(article,
                                                                                                                      name_code_dict)
                                    self.db_obj.insert_data(self.db_name, self.col_name,
                                                            {"Date": date,
                                                             # "PageId": page_url.split("/")[-1],
                                                             "Url": a["href"],
                                                             "Title": a.string,
                                                             "Article": article,
                                                             "RelatedStockCodes": " ".join(related_stock_codes_list)})
                                    self.redis_client.lpush(config.CACHE_NEWS_LIST_NAME, json.dumps(
                                        {"Date": date,
                                         # "PageId": page_url.split("/")[-1],
                                         "Url": a["href"],
                                         "Title": a.string,
                                         "Article": article,
                                         "RelatedStockCodes": " ".join(related_stock_codes_list),
                                         "OriDB": config.DATABASE_NAME,
                                         "OriCOL": config.COLLECTION_NAME_NBD
                                         }
                                    ))
                                    # crawled_urls.append(a["href"])
                                    self.redis_client.lpush(config.CACHE_SAVED_NEWS_NBD_TODAY_VAR_NAME, a["href"])
                                    logging.info("[SUCCESS] {} {} {}".format(date, a.string, a["href"]))
            # logging.info("sleep {} secs then request again ... ".format(interval))
            time.sleep(interval)


# """
# Example-1:
# 爬取历史新闻数据
# """
# if __name__ == "__main__":
#     nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
#     nbd_spyder.get_historical_news(start_page=684)
#
#     Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
#     DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()


# """
# Example-2:
# 爬取实时新闻数据
# """
# if __name__ == '__main__':
#     from Kite import config
#
#     from Killua.denull import DeNull
#     from Killua.deduplication import Deduplication
#
#     from Gon.nbdspyder import NbdSpyder
#
#     # 如果没有历史数据从头爬取，如果已爬取历史数据，则从最新的时间开始爬取
#     # 如历史数据中最近的新闻时间是"2020-12-09 20:37:10"，则从该时间开始爬取
#     nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
#     nbd_spyder.get_historical_news()
#
#     Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
#     DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
#
#     nbd_spyder.get_realtime_news()
