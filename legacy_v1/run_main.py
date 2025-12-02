import time, datetime, threading
from concurrent import futures

from Crawler.crawler_sina import WebCrawlFromSina
from Crawler.crawler_jrj import WebCrawlFromjrj
from Crawler.crawler_cnstock import WebCrawlFromcnstock
from Crawler.crawler_stcn import WebCrawlFromstcn

import Text_Analysis.text_mining as tm

def crawlers(web):
	if web == 'sina':
		web_crawl_obj = WebCrawlFromSina(5000,100,ThreadsNum=4,IP="localhost",PORT=27017,\
			dbName="Sina_Stock",collectionName="sina_news_company")
		web_crawl_obj.classifyRealtimeStockNews()
	elif web == 'jrj':
		web_crawl_obj = WebCrawlFromjrj("2009-01-05","2018-02-03",100,ThreadsNum=4,IP="localhost",PORT=27017,\
			dbName="Jrj_Stock",collectionName="jrj_news_company")
		web_crawl_obj.classifyRealtimeStockNews()
	elif web == 'cnstock':
		web_crawl_obj = WebCrawlFromcnstock(IP="localhost",PORT=27017,ThreadsNum=4,\
			dbName="Cnstock_Stock",collectionName="cnstock_news_company")
		web_crawl_obj.classifyRealtimeStockNews()
	elif web == 'stcn':
		web_crawl_obj = WebCrawlFromstcn(IP="localhost",PORT=27017,ThreadsNum=4,\
			dbName="Stcn_Stock",collectionName="stcn_news_company")
		web_crawl_obj.classifyRealtimeStockNews()

if __name__ == '__main__':
	# Step 1. Initiate
	text_mining_obj = tm.TextMining(IP="localhost",PORT=27017)

	# Step 2. Extract relevant stock codes of news(articles/documents) from all database
	text_mining_obj.extractStockCodeFromArticle("NBD_Stock","nbd_news_company") # 从每经网的新闻中抽出相关的股票代码
	text_mining_obj.extractStockCodeFromArticle("Cnstock_Stock","cnstock_news_company") # 从中国证券网的新闻中抽出相关的股票代码
	text_mining_obj.extractStockCodeFromArticle("Stcn_Stock","stcn_news_company") # 从证券时报网的新闻中抽出相关的股票代码
	text_mining_obj.extractStockCodeFromArticle("Jrj_Stock","jrj_news_company") # 从金融界网的新闻中抽出相关的股票代码

	# Step 3. Extract all news related to specific stock to new database(this step will take long time)
	codeLst = text_mining_obj.extractData("Stock","Basic_Info",['code']).code
	Range = 10
	Idx = 0
	while Idx < len(codeLst):
		thread_lst = []
		for stockcode in codeLst[Idx:Idx+Range]:
			thread = threading.Thread(target=text_mining_obj.getNewsOfSpecificStock,\
				args=([("NBD_Stock","nbd_news_company"),("Sina_Stock","sina_news_company"),\
				("Cnstock_Stock","cnstock_news_company"),("Stcn_Stock","stcn_news_company"),("Jrj_Stock",\
				"jrj_news_company")],stockcode),kwargs={"export":['database','Stock_News',stockcode],"judgeTerm":3})
			thread_lst.append(thread)
		for thread in thread_lst:
			thread.start()
		for thread in thread_lst:
			thread.join()
		print(' [*] have extracted ' + codeLst[Idx:Idx+Range])
		Idx += Range
	thread_lst = []
	for stockcode in codeLst[Idx:]:
		thread = threading.Thread(target=text_mining_obj.getNewsOfSpecificStock,\
			args=([("NBD_Stock","nbd_news_company"),("Sina_Stock","sina_news_company"),\
			("Cnstock_Stock","cnstock_news_company"),("Stcn_Stock","stcn_news_company"),("Jrj_Stock",\
			"jrj_news_company")],stockcode),kwargs={"export":['database','Stock_News',stockcode],"judgeTerm":3})
		thread_lst.append(thread)
	for thread in thread_lst:
		thread.start()
	for thread in thread_lst:
		thread.join()
	print(' [*] have extracted ' + codeLst[Idx:Idx+Range])

	# Step 4. Crawl real-time news from 'web_list' and make classification 
	web_list = ['sina','jrj','cnstock','stcn']
	with futures.ThreadPoolExecutor(max_workers=4) as executor:
		future_to_url = {executor.submit(crawlers,param) : \
			ind for ind, param in enumerate(web_list)}
