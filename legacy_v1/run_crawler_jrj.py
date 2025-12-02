from Crawler.crawler_jrj import WebCrawlFromjrj

if __name__ == '__main__':
    web_crawl_obj = WebCrawlFromjrj("2009-01-05","2018-02-03",100,ThreadsNum=4,IP="localhost",PORT=27017,\
        dbName="Jrj_Stock",collectionName="jrj_news_company")
    web_crawl_obj.coroutine_run()  #web_crawl_obj.single_run() #web_crawl_obj.multi_threads_run()