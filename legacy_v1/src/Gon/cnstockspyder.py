"""
中国证券网：https://www.cnstock.com
公司聚焦：https://company.cnstock.com/company/scp_gsxw
公告解读：https://ggjd.cnstock.com/gglist/search/qmtbbdj
公告快讯：https://ggjd.cnstock.com/gglist/search/ggkx
利好公告：https://ggjd.cnstock.com/company/scp_ggjd/tjd_sdlh
"""

import __init__

from spyder import Spyder

from Kite import utils
from Kite import config
from Kite.database import Database

from Killua.denull import DeNull
from Killua.deduplication import Deduplication

from Leorio.tokenization import Tokenization

import re
import time
import json
import redis
import random
import logging
import threading
from bs4 import BeautifulSoup
from selenium import webdriver

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class CnStockSpyder(Spyder):

    def __init__(self, database_name, collection_name):
        super(CnStockSpyder, self).__init__()
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
            if "class" in span.attrs and span["class"] == ["timer"]:
                date = span.text
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

    def get_historical_news(self, url, category_chn=None, start_date=None):
        """
        :param url: 爬虫网页
        :param category_chn: 所属类别, 中文字符串, 包括'公司聚焦', '公告解读', '公告快讯', '利好公告'
        :param start_date: 数据库中category_chn类别新闻最近一条数据的时间
        """
        assert category_chn is not None
        driver = webdriver.Chrome(executable_path=config.CHROME_DRIVER)
        btn_more_text = ""
        crawled_urls_list = self.extract_data(["Url"])[0]
        logging.info("historical data length -> {} ... ".format(len(crawled_urls_list)))
        # crawled_urls_list = []
        driver.get(url)
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        if start_date is None:
            while btn_more_text != "没有更多":
                more_btn = driver.find_element_by_id('j_more_btn')
                btn_more_text = more_btn.text
                logging.info("1-{}".format(more_btn.text))
                if btn_more_text == "加载更多":
                    more_btn.click()
                    time.sleep(random.random())  # sleep random time less 1s
                elif btn_more_text == "加载中...":
                    time.sleep(random.random()+2)
                    more_btn = driver.find_element_by_id('j_more_btn')
                    btn_more_text = more_btn.text
                    logging.info("2-{}".format(more_btn.text))
                    if btn_more_text == "加载更多":
                        more_btn.click()
                else:
                    more_btn.click()
                    break
            bs = BeautifulSoup(driver.page_source, "html.parser")
            for li in bs.find_all("li", attrs={"class": ["newslist"]}):
                a = li.find_all("h2")[0].find("a")
                if a["href"] not in crawled_urls_list:
                    result = self.get_url_info(a["href"])
                    while not result:
                        self.terminated_amount += 1
                        if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                            # 始终无法爬取的URL保存起来
                            with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                file.write("{}\n".format(a["href"]))
                            logging.info("rejected by remote server longer than {} minutes, "
                                         "and the failed url has been written in path {}"
                                         .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                 config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
                            break
                        logging.info("rejected by remote server, request {} again after "
                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                        time.sleep(60 * self.terminated_amount)
                        result = self.get_url_info(a["href"])
                    if not result:
                        # 爬取失败的情况
                        logging.info("[FAILED] {} {}".format(a["title"], a["href"]))
                    else:
                        # 有返回但是article为null的情况
                        date, article = result
                        while article == "" and self.is_article_prob >= .1:
                            self.is_article_prob -= .1
                            result = self.get_url_info(a["href"])
                            while not result:
                                self.terminated_amount += 1
                                if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                                    # 始终无法爬取的URL保存起来
                                    with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                        file.write("{}\n".format(a["href"]))
                                    logging.info("rejected by remote server longer than {} minutes, "
                                                 "and the failed url has been written in path {}"
                                                 .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                         config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
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
                                    "Category": category_chn,
                                    "Url": a["href"],
                                    "Title": a["title"],
                                    "Article": article,
                                    "RelatedStockCodes": " ".join(related_stock_codes_list)}
                            # self.col.insert_one(data)
                            self.db_obj.insert_data(self.db_name, self.col_name, data)
                            logging.info("[SUCCESS] {} {} {}".format(date, a["title"], a["href"]))
        else:
            # 当start_date不为None时，补充历史数据
            is_click_button = True
            start_get_url_info = False
            tmp_a = None
            while is_click_button:
                bs = BeautifulSoup(driver.page_source, "html.parser")
                for li in bs.find_all("li", attrs={"class": ["newslist"]}):
                    a = li.find_all("h2")[0].find("a")
                    if tmp_a is not None and a["href"] != tmp_a:
                        continue
                    elif tmp_a is not None and a["href"] == tmp_a:
                        start_get_url_info = True
                    if start_get_url_info:
                        date, _ = self.get_url_info(a["href"])
                        if date <= start_date:
                            is_click_button = False
                            break
                tmp_a = a["href"]
                if is_click_button:
                    more_btn = driver.find_element_by_id('j_more_btn')
                    more_btn.click()
            # 从一开始那条新闻到tmp_a都是新增新闻，不包括tmp_a
            bs = BeautifulSoup(driver.page_source, "html.parser")
            for li in bs.find_all("li", attrs={"class": ["newslist"]}):
                a = li.find_all("h2")[0].find("a")
                if a["href"] != tmp_a:
                    result = self.get_url_info(a["href"])
                    while not result:
                        self.terminated_amount += 1
                        if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                            # 始终无法爬取的URL保存起来
                            with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                file.write("{}\n".format(a["href"]))
                            logging.info("rejected by remote server longer than {} minutes, "
                                         "and the failed url has been written in path {}"
                                         .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                 config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
                            break
                        logging.info("rejected by remote server, request {} again after "
                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                        time.sleep(60 * self.terminated_amount)
                        result = self.get_url_info(a["href"])
                    if not result:
                        # 爬取失败的情况
                        logging.info("[FAILED] {} {}".format(a["title"], a["href"]))
                    else:
                        # 有返回但是article为null的情况
                        date, article = result
                        while article == "" and self.is_article_prob >= .1:
                            self.is_article_prob -= .1
                            result = self.get_url_info(a["href"])
                            while not result:
                                self.terminated_amount += 1
                                if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                                    # 始终无法爬取的URL保存起来
                                    with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                        file.write("{}\n".format(a["href"]))
                                    logging.info("rejected by remote server longer than {} minutes, "
                                                 "and the failed url has been written in path {}"
                                                 .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                         config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
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
                                    "Category": category_chn,
                                    "Url": a["href"],
                                    "Title": a["title"],
                                    "Article": article,
                                    "RelatedStockCodes": " ".join(related_stock_codes_list)}
                            # self.col.insert_one(data)
                            self.db_obj.insert_data(self.db_name, self.col_name, data)
                            logging.info("[SUCCESS] {} {} {}".format(date, a["title"], a["href"]))
                else:
                    break
        driver.quit()

    def get_realtime_news(self, url, category_chn=None, interval=60):
        logging.info("start real-time crawling of URL -> {}, request every {} secs ... ".format(url, interval))
        assert category_chn is not None
        # TODO: 由于cnstock爬取的数据量并不大，这里暂时是抽取历史所有数据进行去重，之后会修改去重策略
        name_code_df = self.db_obj.get_data(config.STOCK_DATABASE_NAME,
                                            config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                            keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        crawled_urls = self.db_obj.get_data(self.db_name,
                                            self.col_name,
                                            keys=["Url"])["Url"].to_list()
        while True:
            # 每隔一定时间轮询该网址
            bs = utils.html_parser(url)
            for li in bs.find_all("li", attrs={"class": ["newslist"]}):
                a = li.find_all("h2")[0].find("a")
                if a["href"] not in crawled_urls:  # latest_3_days_crawled_href
                    result = self.get_url_info(a["href"])
                    while not result:
                        self.terminated_amount += 1
                        if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                            # 始终无法爬取的URL保存起来
                            with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                file.write("{}\n".format(a["href"]))
                            logging.info("rejected by remote server longer than {} minutes, "
                                         "and the failed url has been written in path {}"
                                         .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                 config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
                            break
                        logging.info("rejected by remote server, request {} again after "
                                     "{} seconds...".format(a["href"], 60 * self.terminated_amount))
                        time.sleep(60 * self.terminated_amount)
                        result = self.get_url_info(a["href"])
                    if not result:
                        # 爬取失败的情况
                        logging.info("[FAILED] {} {}".format(a["title"], a["href"]))
                    else:
                        # 有返回但是article为null的情况
                        date, article = result
                        while article == "" and self.is_article_prob >= .1:
                            self.is_article_prob -= .1
                            result = self.get_url_info(a["href"])
                            while not result:
                                self.terminated_amount += 1
                                if self.terminated_amount > config.CNSTOCK_MAX_REJECTED_AMOUNTS:
                                    # 始终无法爬取的URL保存起来
                                    with open(config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH, "a+") as file:
                                        file.write("{}\n".format(a["href"]))
                                    logging.info("rejected by remote server longer than {} minutes, "
                                                 "and the failed url has been written in path {}"
                                                 .format(config.CNSTOCK_MAX_REJECTED_AMOUNTS,
                                                         config.RECORD_CNSTOCK_FAILED_URL_TXT_FILE_PATH))
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
                                                     "Category": category_chn,
                                                     "Url": a["href"],
                                                     "Title": a["title"],
                                                     "Article": article,
                                                     "RelatedStockCodes": " ".join(related_stock_codes_list)})
                            self.redis_client.lpush(config.CACHE_NEWS_LIST_NAME, json.dumps(
                                {"Date": date,
                                 "Category": category_chn,
                                 "Url": a["href"],
                                 "Title": a["title"],
                                 "Article": article,
                                 "RelatedStockCodes": " ".join(related_stock_codes_list),
                                 "OriDB": config.DATABASE_NAME,
                                 "OriCOL": config.COLLECTION_NAME_CNSTOCK
                                 }
                            ))
                            logging.info("[SUCCESS] {} {} {}".format(date, a["title"], a["href"]))
                            crawled_urls.append(a["href"])
            # logging.info("sleep {} secs then request {} again ... ".format(interval, url))
            time.sleep(interval)


# """
# Example-1:
# 爬取历史新闻数据
# """
# if __name__ == '__main__':
#     import time
#     import logging
#     from Kite import config
#     from Killua.denull import DeNull
#     from Killua.deduplication import Deduplication
#     from Gon.cnstockspyder import CnStockSpyder
#
#     cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
#     for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
#         logging.info("start crawling {} ...".format(url_to_be_crawled))
#         cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn)
#         logging.info("finished ...")
#         time.sleep(30)
#
#     Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
#     DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()


# """
# Example-2:
# 爬取实时新闻数据
# """
# if __name__ == '__main__':
#     import time, logging, threading
#     from Kite import config
#     from Kite.database import Database
#     from Killua.denull import DeNull
#     from Killua.deduplication import Deduplication
#     from Gon.cnstockspyder import CnStockSpyder
#
#     obj = Database()
#     df = obj.get_data(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK, keys=["Date", "Category"])
#
#     cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
#     # 先补充历史数据，比如已爬取数据到2020-12-01，但是启动实时爬取程序在2020-12-23，则先
#     # 自动补充爬取2020-12-02至2020-12-23的新闻数据
#     for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
#         # 查询type_chn的最近一条数据的时间
#         latets_date_in_db = max(df[df.Category == type_chn]["Date"].to_list())
#         cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn, start_date=latets_date_in_db)
#
#     Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
#     DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
#
#     # 开启多线程并行实时爬取
#     thread_list = []
#     for url, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
#         thread = threading.Thread(target=cnstock_spyder.get_realtime_news, args=(url, type_chn, 60))
#         thread_list.append(thread)
#     for thread in thread_list:
#         thread.start()
#     for thread in thread_list:
#         thread.join()
