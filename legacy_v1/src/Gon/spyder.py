class Spyder(object):

    def __init__(self):
        self.is_article_prob = .5

    def extract_data(self, tag_list):
        data = list()
        for tag in tag_list:
            exec(tag + " = self.col.distinct('" + tag + "')")
            exec("data.append(" + tag + ")")

        return data

    def query_news(self, _key, param):
        # 模糊查询
        return self.col.find({_key: {'$regex': ".*{}.*".format(param)}})

    def get_url_info(self, url):
        pass

    def get_historical_news(self, url):
        pass

    def get_realtime_news(self, url):
        pass