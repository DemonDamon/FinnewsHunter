# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 10:01:40 2018

@author: Damon Li
"""

import time, re, requests
from concurrent import futures
from bs4 import BeautifulSoup
from pymongo import MongoClient
import Text_Analysis.text_mining as tm

import gevent
from gevent import monkey,pool
monkey.patch_all()


class WebCrawlFromSina(object):
    '''Crawl company news from 'http://roll.finance.sina.com.cn/finance/zq1/ssgs/index.shtml' website.

    # Arguments:
        totalPages: Number of pages set to be crawled(int type).
        Range: Divide total web pages into totalPages/Range parts 
               for multi-threading processing(int type).
        ThreadsNum: Number of threads needed to be start(int type).
        dbName: Name of database(string type).
        colName: Name of collection(string type).
        IP: Local IP address(string type).
        PORT: Port number corresponding to IP address(int type).
    '''

    def __init__(self,*arg,**kwarg):
        self.totalPages = arg[0] #totalPages
        self.Range = arg[1] #Range
        self.ThreadsNum = kwarg['ThreadsNum']
        self.dbName = kwarg['dbName']
        self.colName = kwarg['collectionName']
        self.IP = kwarg['IP']
        self.PORT = kwarg['PORT']
        self.Porb = .5 
        self.realtimeNewsURL = []
        self.tm = tm.TextMining(IP="localhost",PORT=27017)

    def countchn(self,string):
        '''Count Chinese numbers and calculate the frequency of Chinese occurrence.

        # Arguments:
            string: Each part of crawled website analyzed by BeautifulSoup.
        '''
        pattern = re.compile(u'[\u1100-\uFFFDh]+?')
        result = pattern.findall(string)
        chnnum = len(result)
        possible = chnnum/len(str(string))
        return (chnnum, possible)

    def getUrlInfo(self,url):
        '''Analyze website and extract useful information.
        '''
        respond = requests.get(url)
        respond.encoding = BeautifulSoup(respond.content, "lxml").original_encoding
        bs = BeautifulSoup(respond.text, "lxml")
        meta_list = bs.find_all('meta')
        span_list = bs.find_all('span')
        part = bs.find_all('p')
        article = ''
        date = ''
        summary = ''
        keyWords = ''
        stockCodeLst = ''
        for meta in meta_list:
            if 'name' in meta.attrs and meta['name'] == 'description':
                summary = meta['content']
            elif 'name' in meta.attrs and meta['name'] == 'keywords':
                keyWords = meta['content']
            if summary != '' and keyWords != '':
                break
        for span in span_list:
            if 'class' in span.attrs:
                if span['class'] == ['date'] or span['class'] == ['time-source']:
                    string = span.text.split()
                    for dt in string:
                        if dt.find('年') != -1:
                            date += dt.replace('年','-').replace('月','-').replace('日',' ')
                        elif dt.find(':') != -1:
                            date += dt
                    break
            if 'id' in span.attrs and span['id'] == 'pub_date':
                string = span.text.split()
                for dt in string:
                    if dt.find('年') != -1:
                        date += dt.replace('年','-').replace('月','-').replace('日',' ')
                    elif dt.find(':') != -1:
                        date += dt
                break
        for span in span_list:
            if 'id' in span.attrs and span['id'].find('stock_') != -1:
                stockCodeLst += span['id'][8:] + ' '

        for paragraph in part:
            chnstatus = self.countchn(str(paragraph))
            possible = chnstatus[1]
            '''Porb: Standard frequency of Chinese occurrence among 
               each parts of one news(article/document), used
               to judge whether any part is main body or not.
            '''
            if possible > self.Porb:
               article += str(paragraph)

        time1 = time.time()
        while article.find('<') != -1 and article.find('>') != -1:
              string = article[article.find('<'):article.find('>')+1]
              article = article.replace(string,'')
              time2 = time.time()
              if time2 - time1 > 60:
                print(' [*] 循环超时60s，跳出循环 ... ')
                break

        time1 = time.time()
        while article.find('\u3000') != -1:
              article = article.replace('\u3000','')
              time2 = time.time()
              if time2 - time1 > 60:
                print(' [*] 循环超时60s，跳出循环 ... ')
                break

        article = ' '.join(re.split(' +|\n+', article)).strip() 

        return summary, keyWords, date, stockCodeLst, article

    def GenPagesLst(self):
        '''Generate page number list using Range parameter.
        '''
        PageLst = []
        k = 1
        while k+self.Range-1 <= self.totalPages:
            PageLst.append((k,k+self.Range-1))
            k += self.Range
        if k+self.Range-1 < self.totalPages:
            PageLst.append((k,self.totalPages))
        return PageLst

    def CrawlRealtimeCompanyNews(self,firstPage): 
        '''Continue crawling company news from first website page
           every once in a while and extract the useful information, 
           including summary, key words, released date, related stock 
           codes list and main body.
        '''
        doc_lst = []
        if len(self.realtimeNewsURL) == 0:
            self.ConnDB()
            self._AddressLst = self.extractData(['Address'])[0]
            resp = requests.get(firstPage)
            resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
            bs = BeautifulSoup(resp.text, "lxml")
            a_list = bs.find_all('a')
            for a in a_list:
                if 'href' in a.attrs and a.string and \
                a['href'].find('http://finance.sina.com.cn/stock/s/') != -1:
                    if a['href'] not in self._AddressLst:
                        self.realtimeNewsURL.append(a['href'])
                        summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        while article == '' and self.Prob >= .1:
                            self.Prob -= .1
                            summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a.string,
                                    'Keywords' : keyWords,
                                    'Summary' : summary,
                                    'Article' : article,
                                    'RelevantStock' : stockCodeLst}
                            self._collection.insert_one(data)
                            doc_lst.append(a.string + ' ' + summary + ' ' + article)
                            print(' [' + date + '] ' + a.string)
        else:
            resp = requests.get(firstPage)
            resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
            bs = BeautifulSoup(resp.text, "lxml")
            a_list = bs.find_all('a')
            for a in a_list:
                if 'href' in a.attrs and a.string and \
                a['href'].find('http://finance.sina.com.cn/stock/s/') != -1:
                    if a['href'] not in self.realtimeNewsURL and a['href'] not in self._AddressLst:
                        self.realtimeNewsURL.append(a['href'])
                        summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        while article == '' and self.Prob >= .1:
                            self.Prob -= .1
                            summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a.string,
                                    'Keywords' : keyWords,
                                    'Summary' : summary,
                                    'Article' : article,
                                    'RelevantStock' : stockCodeLst}
                            self._collection.insert_one(data)
                            doc_lst.append(a.string + ' ' + summary + ' ' + article)
                            print(' [' + date + '] ' + a.string)
        return doc_lst

    def CrawlHistoryCompanyNews(self,startPage,endPage):
        '''Crawl historical company news 
        '''
        self.ConnDB()
        AddressLst = self.extractData(['Address'])[0]
        if AddressLst == []:
            urls = []
            url_Part_1 = 'http://roll.finance.sina.com.cn/finance/zq1/ssgs/index_' 
            url_Part_2 = '.shtml'
            for pageId in range(startPage,endPage+1):
                urls.append(url_Part_1 + str(pageId) + url_Part_2)
            for url in urls:
                print(url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('http://finance.sina.com.cn/stock/s/') != -1:
                        summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        while article == '' and self.Prob >= .1:
                            self.Prob -= .1
                            summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a.string,
                                    'Keywords' : keyWords,
                                    'Summary' : summary,
                                    'Article' : article,
                                    'RelevantStock' : stockCodeLst}
                            self._collection.insert_one(data)
        else:
            urls = []
            url_Part_1 = 'http://roll.finance.sina.com.cn/finance/zq1/ssgs/index_' 
            url_Part_2 = '.shtml'
            for pageId in range(startPage,endPage+1):
                urls.append(url_Part_1 + str(pageId) + url_Part_2)
            for url in urls:
                print(' <Re-Crawl url> ', url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('http://finance.sina.com.cn/stock/s/') != -1:
                        if a['href'] not in AddressLst:
                            summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                summary, keyWords, date, stockCodeLst, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a.string,
                                        'Keywords' : keyWords,
                                        'Summary' : summary,
                                        'Article' : article,
                                        'RelevantStock' : stockCodeLst}
                                self._collection.insert_one(data)

    def ConnDB(self):
        '''Connect mongodb.
        '''
        Conn = MongoClient(self.IP, self.PORT) 
        db = Conn[self.dbName]
        self._collection = db.get_collection(self.colName)

    def extractData(self,tag_list):
        '''Extract column data with tag in 'tag_list' to the list.
        '''
        data = []
        for tag in tag_list:
            exec(tag + " = self._collection.distinct('" + tag + "')")
            exec("data.append(" + tag + ")")
        return data

    def single_run(self):
        '''Single threading running.
        '''
        page_ranges_lst = self.GenPagesLst()
        for ind, page_range in enumerate(page_ranges_lst):
            self.CrawlHistoryCompanyNews(page_range[0],page_range[1]) 

    def coroutine_run(self):
        '''Coroutines running.
        '''
        jobs = []
        page_ranges_lst = self.GenPagesLst()
        for page_range in page_ranges_lst:
            jobs.append(gevent.spawn(self.CrawlHistoryCompanyNews,page_range[0],page_range[1]))
        gevent.joinall(jobs) 

    def multi_threads_run(self,**kwarg):
        '''Multi-threading running.
        '''
        page_ranges_lst = self.GenPagesLst()
        print(' Using ' + str(self.ThreadsNum) + ' threads for collecting news ... ')
        with futures.ThreadPoolExecutor(max_workers=self.ThreadsNum) as executor:
            future_to_url = {executor.submit(self.CrawlHistoryCompanyNews,page_range[0],page_range[1]) : \
                             ind for ind, page_range in enumerate(page_ranges_lst)}  

    def classifyRealtimeStockNews(self):
        '''Continue crawling and classifying news(articles/documents) every 60s. 
        '''
        while True:
            print(' * start crawling news from SINA ... ')
            doc_list = self.CrawlRealtimeCompanyNews('http://roll.finance.sina.com.cn/finance/zq1/ssgs/index_1.shtml') #
            print(' * finish crawling ... ')
            if len(doc_list) != 0:
                self.tm.classifyRealtimeStockNews(doc_list)
            time.sleep(60)

if __name__ == '__main__':
    web_crawl_obj = WebCrawlFromSina(5000,100,ThreadsNum=4,IP="localhost",PORT=27017,\
        dbName="Sina_Stock",collectionName="sina_news_company")
    web_crawl_obj.coroutine_run()  #web_crawl_obj.single_run() #web_crawl_obj.multi_threads_run()