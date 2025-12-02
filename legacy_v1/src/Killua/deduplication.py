import __init__

from Kite.database import Database
from Kite import utils

import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class Deduplication(object):

    def __init__(self, database_name, collection_name):
        self.database = Database()
        self.database_name = database_name
        self.collection_name = collection_name
        self.delete_num = 0

    def run(self):
        date_list = self.database.get_data(self.database_name,
                                           self.collection_name,
                                           keys=["Date"])["Date"].tolist()
        collection = self.database.get_collection(self.database_name, self.collection_name)
        date_list.sort()  # 升序
        # start_date, end_date = date_list[1].split(" ")[0], date_list[-1].split(" ")[0]
        start_date, end_date = min(date_list).split(" ")[0], max(date_list).split(" ")[0]
        for _date in utils.get_date_list_from_range(start_date, end_date):
            # 获取特定时间对应的数据并根据URL去重
            # logging.info(_date)
            try:
                data_df = self.database.get_data(self.database_name,
                                                 self.collection_name,
                                                 query={"Date": {"$regex": _date}})
            except Exception:
                continue
            if data_df is None:
                continue
            data_df_drop_duplicate = data_df.drop_duplicates(["Url"])
            for _id in list(set(data_df["_id"]) - set(data_df_drop_duplicate["_id"])):
                collection.delete_one({'_id': _id})
                self.delete_num += 1
            # logging.info("{} finished ... ".format(_date))
        logging.info("DB:{} - COL:{} had {} data length originally, now has deleted {} depulications ... "
                     .format(self.database_name, self.collection_name, str(len(date_list)), self.delete_num))


if __name__ == "__main__":
    from Killua.deduplication import Deduplication
    from Kite import config

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()




