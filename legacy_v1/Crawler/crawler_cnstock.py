# -*- coding: utf-8 -*-
"""
Created on Sat Feb 3 13:41:50 2018

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


class WebCrawlFromcnstock(object):
    '''Crawl company news from 'http://company.cnstock.com/company/scp_gsxw/1',
                               'http://ggjd.cnstock.com/gglist/search/qmtbbdj/1',
                               'http://ggjd.cnstock.com/gglist/search/ggkx/1' website.

    # Arguments:
        totalPages: Number of pages set to be crawled.
        Range: Divide total web pages into totalPages/Range parts 
               for multi-threading processing.
        ThreadsNum: Number of threads needed to be start.
        dbName: Name of database.
        colName: Name of collection.
        IP: Local IP address.
        PORT: Port number corresponding to IP address.
    '''

    def __init__(self,**kwarg):
        self.ThreadsNum = kwarg['ThreadsNum']
        self.dbName = kwarg['dbName']
        self.colName = kwarg['collectionName']
        self.IP = kwarg['IP']
        self.PORT = kwarg['PORT']
        self.Prob = .5
        self.realtimeNewsURL = []
        self.tm = tm.TextMining(IP="localhost",PORT=27017)

    def ConnDB(self):
        '''Connect mongodb.
        '''
        Conn = MongoClient(self.IP, self.PORT) 
        db = Conn[self.dbName]
        self._collection = db.get_collection(self.colName)

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
        span_list = bs.find_all('span')
        part = bs.find_all('p')
        article = ''
        date = ''
        for span in span_list:
            if 'class' in span.attrs and span['class'] == ['timer']:
                date = span.text
                break

        for paragraph in part:
            chnstatus = self.countchn(str(paragraph))
            possible = chnstatus[1]
            if possible > self.Prob:
               article += str(paragraph)

        while article.find('<') != -1 and article.find('>') != -1:
              string = article[article.find('<'):article.find('>')+1]
              article = article.replace(string,'')
        while article.find('\u3000') != -1:
              article = article.replace('\u3000','')

        article = ' '.join(re.split(' +|\n+', article)).strip() 

        return date, article

    def GenPagesLst(self,totalPages,Range,initPageID):
        '''Generate page number list using Range parameter.
        '''
        PageLst = []
        k = initPageID
        while k+Range-1 <= totalPages:
            PageLst.append((k,k+Range-1))
            k += Range
        if k+Range-1 < totalPages:
            PageLst.append((k,totalPages))
        return PageLst

    def CrawlHistoryCompanyNews(self,startPage,endPage,url_Part_1):
        '''Crawl historical company news 
        '''
        self.ConnDB()
        AddressLst = self.extractData(['Address'])[0]
        if AddressLst == []:
            urls = []
            for pageId in range(startPage,endPage+1):
                urls.append(url_Part_1 + str(pageId))
            for url in urls:
                print(url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span'):
                        date, article = self.getUrlInfo(a['href'])
                        while article == '' and self.Prob >= .1:
                            self.Prob -= .193
                            date, article = self.getUrlInfo(a['href'])
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a['title'],
                                    'Article' : article}
                            self._collection.insert_one(data)
        else:
            urls = []
            for pageId in range(startPage,endPage+1):
                urls.append(url_Part_1 + str(pageId))
            for url in urls:
                print(' <Re-Crawl url> ', url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span'):
                        if a['href'] not in AddressLst:
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)

    def CrawlRealtimeCompanyNews(self,url_part_lst):
        '''Continue crawling company news from first website page 
           every once in a while and extract the useful information, 
           including summary, key words, released date, related stock 
           codes list and main body.
        '''
        doc_lst = []
        self.ConnDB()
        self._AddressLst = self.extractData(['Address'])[0]
        for url_Part in url_part_lst:
            url = url_Part + str(1)
            resp = requests.get(url)
            resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
            bs = BeautifulSoup(resp.text, "lxml")
            a_list = bs.find_all('a')
            if len(self.realtimeNewsURL) == 0:
                for a in a_list:
                    if ('href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span')) or ('href' in a.attrs and 'target' in a.attrs \
                    and 'title' in a.attrs and a['href'].find('http://ggjd.cnstock.com/company/') != -1 \
                    and a.parent.find('span')):
                        if a['href'] not in self._AddressLst:
                            self.realtimeNewsURL.append(a['href'])
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a['title'] + ' ' + article)
                                print(' [' + date + '] ' + a['title'])
            else:
                for a in a_list:
                    if ('href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span')) or ('href' in a.attrs and 'target' in a.attrs \
                    and 'title' in a.attrs and a['href'].find('http://ggjd.cnstock.com/company/') != -1 \
                    and a.parent.find('span')):
                        if a['href'] not in self.realtimeNewsURL and a['href'] not in self._AddressLst:
                            self.realtimeNewsURL.append(a['href'])
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a['title'] + ' ' + article)
                                print(' [' + date + '] ' + a['title'])
        return doc_lst

    def extractData(self,tag_list):
        '''Extract column data with tag in 'tag_list' to the list.
        '''
        data = []
        for tag in tag_list:
            exec(tag + " = self._collection.distinct('" + tag + "')")
            exec("data.append(" + tag + ")")
        return data

    def coroutine_run(self,totalPages,Range,initPageID,**kwarg):
        '''Coroutines running.
        '''
        jobs = []
        page_ranges_lst = self.GenPagesLst(totalPages,Range,initPageID)
        for page_range in page_ranges_lst:
            jobs.append(gevent.spawn(self.CrawlHistoryCompanyNews,page_range[0],page_range[1],kwarg['url_Part_1']))
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
            print(' * start crawling news from CNSTOCK ... ')
            doc_list = self.CrawlRealtimeCompanyNews(['http://company.cnstock.com/company/scp_gsxw/',\
                                                    'http://ggjd.cnstock.com/gglist/search/qmtbbdj/',\
                                                    'http://ggjd.cnstock.com/gglist/search/ggkx/']) #
            print(' * finish crawling ... ')
            if len(doc_list) != 0:
                self.tm.classifyRealtimeStockNews(doc_list)
            time.sleep(60)