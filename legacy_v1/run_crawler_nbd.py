from Crawler.crawler_nbd import WebCrawlFromNBD

if __name__ == '__main__':
    web_crawl_obj = WebCrawlFromNBD(2871,10,ThreadsNum=4,IP="localhost",PORT=27017,dbName='NBD_Stock',\
      collectionName="nbd_news_company")
    url_lst_withoutNews = web_crawl_obj.coroutine_run() #web_crawl_obj.single_run() #web_crawl_obj.multi_threads_run()
    if url_lst_withoutNews != []:
       print(' -------------------- Re-Crawl News List Pages -------------------- ')
       url_lst_withoutArticles, title_lst_withoutArticles = web_crawl_obj.ReCrawlNews(url_lst_withoutNews)
    if url_lst_withoutArticles != [] or title_lst_withoutArticles != []:
       print(' -------------------- Re-Crawl Article Pages -------------------- ')
       web_crawl_obj.ReCrawlArticles(url_lst_withoutArticles,title_lst_withoutArticles)