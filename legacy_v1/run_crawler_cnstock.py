from Crawler.crawler_cnstock import WebCrawlFromcnstock

if __name__ == '__main__':
    web_crawl_obj = WebCrawlFromcnstock(IP="localhost",PORT=27017,ThreadsNum=4,\
        dbName="Cnstock_Stock",collectionName="cnstock_news_company")
    web_crawl_obj.coroutine_run(621,10,1,url_Part_1='http://company.cnstock.com/company/scp_gsxw/') #Obj.multi_threads_run()
    web_crawl_obj.coroutine_run(112,10,0,url_Part_1='http://ggjd.cnstock.com/gglist/search/qmtbbdj/')
    web_crawl_obj.coroutine_run(116,10,0,url_Part_1='http://ggjd.cnstock.com/gglist/search/ggkx/')
   
 