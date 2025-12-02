from Crawler.crawler_stcn import WebCrawlFromstcn

if __name__ == '__main__':
    web_crawl_obj = WebCrawlFromstcn(IP="localhost",PORT=27017,ThreadsNum=4,\
        dbName="Stcn_Stock",collectionName="stcn_news_company")
    web_crawl_obj.coroutine_run(20,1,1,url_Part_1='http://company.stcn.com/gsxw/') 
    web_crawl_obj.coroutine_run(20,1,1,url_Part_1='http://stock.stcn.com/xingu/')
    web_crawl_obj.coroutine_run(20,1,1,url_Part_1='http://stock.stcn.com/zhuli/')
    web_crawl_obj.coroutine_run(20,1,1,url_Part_1='http://stock.stcn.com/bankuai/')
    web_crawl_obj.coroutine_run(20,1,1,url_Part_1='http://stock.stcn.com/dapan/')