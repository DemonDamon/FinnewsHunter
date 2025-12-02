import __init__

from Kite.database import Database
from Kite import config
from Kite import utils

import jieba
import pkuseg
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class Tokenization(object):

    def __init__(self, import_module="jieba", user_dict=None, chn_stop_words_dir=None):
        #self.database = Database().conn[config.DATABASE_NAME]  #.get_collection(config.COLLECTION_NAME_CNSTOCK)
        self.database = Database()
        self.import_module = import_module
        self.user_dict = user_dict
        if self.user_dict:
            self.update_user_dict(self.user_dict)
        if chn_stop_words_dir:
            self.stop_words_list = utils.get_chn_stop_words(chn_stop_words_dir)
        else:
            self.stop_words_list = list()

    def update_user_dict(self, old_user_dict_dir, new_user_dict_dir=None):
        # 将缺失的(或新的)股票名称、金融新词等，添加进金融词典中
        word_list = []
        with open(old_user_dict_dir, "r", encoding="utf-8") as file:
            for row in file:
                word_list.append(row.split("\n")[0])
        name_code_df = self.database.get_data(config.STOCK_DATABASE_NAME,
                                              config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                              keys=["name", "code"])
        new_words_list = list(set(name_code_df["name"].tolist()))
        for word in new_words_list:
            if word not in word_list:
                word_list.append(word)
        new_user_dict_dir = old_user_dict_dir if not new_user_dict_dir else new_user_dict_dir
        with open(new_user_dict_dir, "w", encoding="utf-8") as file:
            for word in word_list:
                file.write(word + "\n")

    def cut_words(self, text):
        outstr = list()
        sentence_seged = None
        if self.import_module == "jieba":
            if self.user_dict:
                jieba.load_userdict(self.user_dict)
            sentence_seged = list(jieba.cut(text))
        elif self.import_module == "pkuseg":
            seg = pkuseg.pkuseg(user_dict=self.user_dict)  # 添加自定义词典
            sentence_seged = seg.cut(text)  # 进行分词
        if sentence_seged:
            for word in sentence_seged:
                if word not in self.stop_words_list \
                        and word != "\t" \
                        and word != " " \
                        and utils.is_contain_chn(word)\
                        and len(word) > 1:
                    outstr.append(word)
            return outstr
        else:
            return False

    def find_relevant_stock_codes_in_article(self, article, stock_name_code_dict):
        stock_codes_set = list()
        cut_words_list = self.cut_words(article)
        if cut_words_list:
            for word in cut_words_list:
                try:
                    stock_codes_set.append(stock_name_code_dict[word])
                except Exception:
                    pass
        return list(set(stock_codes_set))

    def update_news_database_rows(self,
                                  database_name,
                                  collection_name,
                                  incremental_column_name="RelatedStockCodes"):
        name_code_df = self.database.get_data(config.STOCK_DATABASE_NAME,
                                              config.COLLECTION_NAME_STOCK_BASIC_INFO,
                                              keys=["name", "code"])
        name_code_dict = dict(name_code_df.values)
        data = self.database.get_collection(database_name, collection_name).find()
        for row in data:
            # if row["Date"] > "2019-05-20 00:00:00":
            # 在新增数据中，并不存在更新列，但是旧数据中已存在更新列，因此需要
            # 判断数据结构中是否包含该incremental_column_name字段
            if incremental_column_name not in row.keys():
                related_stock_codes_list = self.find_relevant_stock_codes_in_article(
                                             row["Article"], name_code_dict)
                self.database.update_row(database_name,
                                         collection_name,
                                         {"_id": row["_id"]},
                                         {incremental_column_name: " ".join(related_stock_codes_list)}
                                         )
                logging.info("[{} -> {} -> {}] updated {} key value ... "
                             .format(database_name, collection_name, row["Date"], incremental_column_name))
            else:
                logging.info("[{} -> {} -> {}] has already existed {} key value ... "
                             .format(database_name, collection_name, row["Date"], incremental_column_name))


if __name__ == "__main__":
    tokenization = Tokenization(import_module="jieba",
                                user_dict="financedict.txt",
                                chn_stop_words_dir="chnstopwords.txt")
    # documents_list = \
    #     [
    #         "中央、地方支持政策频出,煤炭行业站上了风口 券商研报浩如烟海，投资线索眼花缭乱，\
    #         第一财经推出《一财研选》产品，挖掘研报精华，每期梳理5条投资线索，便于您短时间内获\
    #         取有价值的信息。专业团队每周日至每周四晚8点准时“上新”，助您投资顺利！",
    #         "郭文仓到重点工程项目督导检查 2月2日,公司党委书记、董事长、总经理郭文仓,公司董事,\
    #         股份公司副总经理、总工程师、郭毅民,股份公司副总经理张国富、柴高贵及相关单位负责人到\
    #         焦化厂煤场全封闭和干熄焦等重点工程项目建设工地督导检查施工进度和安全工作情况。"
    #     ]
    # for text in documents_list:
    #     cut_words_list = tokenization.cut_words(text)
    #     print(cut_words_list)
    # tokenization.update_news_database_rows(config.DATABASE_NAME, "jrj")
