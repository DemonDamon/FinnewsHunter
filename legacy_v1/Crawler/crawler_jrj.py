# -*- coding: utf-8 -*-
"""
Created on Sat Feb 3 13:41:50 2018

@author: Damon Li
"""

import time, re, requests, datetime
from concurrent import futures
from bs4 import BeautifulSoup
from pymongo import MongoClient
import Text_Analysis.text_mining as tm
from bson.objectid import ObjectId

import gevent
from gevent import monkey,pool
monkey.patch_all()


class WebCrawlFromjrj(object):
    '''Crawl company news from 'http://roll.finance.sina.com.cn/finance/zq1/ssgs/index.shtml' website.

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

    def __init__(self,*arg,**kwarg):
        self.startDate = arg[0]
        self.endDate = arg[1]
        self.Range = arg[2]
        self.ThreadsNum = kwarg['ThreadsNum']
        self.dbName = kwarg['dbName']
        self.colName = kwarg['collectionName']
        self.IP = kwarg['IP']
        self.PORT = kwarg['PORT']
        self.Prob = .5
        self.realtimeNewsURL = []
        self.tm = tm.TextMining(IP="localhost",PORT=27017)

    def getEveryDay(self,begin_date,end_date):
        '''Get date list from 'begin_date' to 'end_date' on the calendar.
        '''
        date_list = []  
        begin_date = datetime.datetime.strptime(begin_date, "%Y-%m-%d")  
        end_date = datetime.datetime.strptime(end_date,"%Y-%m-%d")  
        while begin_date <= end_date:  
            date_str = begin_date.strftime("%Y-%m-%d")  
            date_list.append(date_str)  
            begin_date += datetime.timedelta(days=1)  
        return date_list  

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

    def getUrlInfo(self,url,specificDate):
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
        NotFoundPage = False
        for span in span_list:
            for child in span.children:
                if child == 'jrj_final_date_start':
                    date = span.text.replace('\r','').replace('\n','')
                    if date.find('年') != -1:
                        date = date.replace('年','-').replace('月','-').replace('日','')
                    break
            break
        if date == '':
            date = specificDate

        for p in part:
            if p.text.find('页面没有找到') != -1:
               NotFoundPage = True
               break

        if not NotFoundPage:
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

        return date, article, NotFoundPage

    def GenDatesLst(self):
        '''Divide date list into parts using Range parameter.
        '''
        DatesLst = self.getEveryDay(self.startDate,self.endDate)
        NewDatesLst = []
        k = 0
        while k < len(DatesLst):
            if k+self.Range >= len(DatesLst):
                break
            else:
                NewDatesLst.append(DatesLst[k:k+self.Range])
                k += self.Range 
        NewDatesLst.append(DatesLst[k:])
        return NewDatesLst

    def findPagesOfSpecificDate(self,firstUrl,date):
        '''Search the number of web pages of specific date.

        # Arguments:
            firstUrl: The first web page of specific date.
            date: Desinated date.
        '''
        respond = requests.get(firstUrl)
        respond.encoding = BeautifulSoup(respond.content, "lxml").original_encoding
        bs = BeautifulSoup(respond.text, "lxml")
        a_list = bs.find_all('a')
        Nums = 1
        for a in a_list:
            if 'href' in a.attrs and 'target' in a.attrs:
                if a['href'].find(date.replace('-','') + '_') != -1 and a.text.isdigit():
                    Nums += 1
        return Nums

    def CrawlRealtimeCompanyNews(self,today_Date): 
        '''Continue crawling company news from first website page
           every once in a while and extract the useful information, 
           including summary, key words, released date, related stock 
           codes list and main body.
        '''
        doc_lst = []
        if len(self.realtimeNewsURL) == 0:
            self.ConnDB()
            self._AddressLst = self.extractData(['Address'])[0]
            urlsAndDates = []
            url_Part_1 = 'http://stock.jrj.com.cn/xwk/'
            url_Part_2 = '_1.shtml'
            firstUrl = url_Part_1 + today_Date.replace('-','')[0:6] + '/' + today_Date.replace('-','') + url_Part_2
            Nums = self.findPagesOfSpecificDate(firstUrl,today_Date)
            for num in range(1,Nums+1):
                urlsAndDates.append((url_Part_1 + today_Date.replace('-','')[0:6] + '/' + today_Date.replace('-','') \
                    + '_' + str(num) + '.shtml', today_Date))
            for url, specificDate in urlsAndDates:
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('/' + specificDate.replace('-','')[0:4] + '/' + specificDate.replace('-','')[4:6] + '/') != -1:
                        if a['href'] not in self._AddressLst:
                            self.realtimeNewsURL.append(a['href'])
                            date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            while article == '' and self.Prob >= .1 and not NotFoundPage:
                                self.Prob -= .1
                                date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a.string,
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a.string + ' ' + article)
                                print(' [' + date + '] ' + a.string)
        else:
            urlsAndDates = []
            url_Part_1 = 'http://stock.jrj.com.cn/xwk/'
            url_Part_2 = '_1.shtml'
            firstUrl = url_Part_1 + today_Date.replace('-','')[0:6] + '/' + today_Date.replace('-','') + url_Part_2
            Nums = self.findPagesOfSpecificDate(firstUrl,today_Date)
            for num in range(1,Nums+1):
                urlsAndDates.append((url_Part_1 + today_Date.replace('-','')[0:6] + '/' + today_Date.replace('-','') \
                    + '_' + str(num) + '.shtml', today_Date))
            for url, specificDate in urlsAndDates:
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('/' + specificDate.replace('-','')[0:4] + '/' + specificDate.replace('-','')[4:6] + '/') != -1:
                        if a['href'] not in self._AddressLst and a['href'] not in self.realtimeNewsURL:
                            self.realtimeNewsURL.append(a['href'])
                            date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            while article == '' and self.Prob >= .1 and not NotFoundPage:
                                self.Prob -= .1
                                date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a.string,
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a.string + ' ' + article)
                                print(' [' + date + '] ' + a.string)
        return doc_lst

    def CrawlHistoryCompanyNews(self,datelst):
        '''Crawl historical company news 
        '''
        self.ConnDB()
        AddressLst = self.extractData(['Address'])[0]
        if AddressLst == []:
            urlsAndDates = []
            url_Part_1 = 'http://stock.jrj.com.cn/xwk/'
            url_Part_2 = '_1.shtml'
            for date in datelst:
                firstUrl = url_Part_1 + date.replace('-','')[0:6] + '/' + date.replace('-','') + url_Part_2
                Nums = self.findPagesOfSpecificDate(firstUrl,date)
                for num in range(1,Nums+1):
                    urlsAndDates.append((url_Part_1 + date.replace('-','')[0:6] + '/' + date.replace('-','') \
                        + '_' + str(num) + '.shtml', date))
            for url, specificDate in urlsAndDates:
                print(url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('/' + specificDate.replace('-','')[0:4] + '/' + specificDate.replace('-','')[4:6] + '/') != -1:
                        date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                        while article == '' and self.Prob >= .1 and not NotFoundPage:
                            self.Prob -= .1
                            date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a.string,
                                    'Article' : article}
                            self._collection.insert_one(data)
        else:
            urlsAndDates = []
            url_Part_1 = 'http://stock.jrj.com.cn/xwk/'
            url_Part_2 = '_1.shtml'
            for date in datelst:
                firstUrl = url_Part_1 + date.replace('-','')[0:6] + '/' + date.replace('-','') + url_Part_2
                Nums = self.findPagesOfSpecificDate(firstUrl,date)
                for num in range(1,Nums+1):
                    urlsAndDates.append((url_Part_1 + date.replace('-','')[0:6] + '/' + date.replace('-','') \
                        + '_' + str(num) + '.shtml', date))
            for url, specificDate in urlsAndDates:
                print(' <Re-Crawl url> ', url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and a.string and \
                    a['href'].find('/' + specificDate.replace('-','')[0:4] + '/' + specificDate.replace('-','')[4:6] + '/') != -1:
                        if a['href'] not in AddressLst:
                            date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            while article == '' and self.Prob >= .1 and not NotFoundPage:
                                self.Prob -= .1
                                date, article, NotFoundPage = self.getUrlInfo(a['href'],specificDate)
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a.string,
                                        'Article' : article}
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

    def StockCodeDuplicateRemoval(self):
        '''Discarded.
        '''
        Conn = MongoClient(self.IP, self.PORT) 
        db = Conn[self.dbName]
        collection = db.get_collection(self.colName)
        idLst = collection.distinct('_id')
        relevantStockSeries = []
        for _id in idLst:
            data = collection.find_one({'_id':ObjectId(_id)})
            if 'relevantStock' in data.keys():
                relevantStock = collection.find_one({'_id':ObjectId(_id)})['relevantStock']
                if len(relevantStock) > 1:
                    relevantStockCodeDuplicateRemoval = list(set(relevantStock))
                    collection.update({"_id":_id},{"$set":{"relevantStock":' '.join(relevantStockCodeDuplicateRemoval)}})
                    print(relevantStockCodeDuplicateRemoval)
                    break
                if len(relevantStock) == 1:
                    print(relevantStock)
                    print(len(relevantStock))
                    break
        print('Duplicate Removal successfully ... ')

    def coroutine_run(self):
        '''Coroutines running.
        '''
        jobs = []
        dateLst = self.GenDatesLst()
        for datelst in dateLst:
            jobs.append(gevent.spawn(self.CrawlHistoryCompanyNews,datelst))
        gevent.joinall(jobs) 

    def multi_threads_run(self,**kwarg):
        '''Multi-threading running.
        '''
        dateLst = self.GenDatesLst()
        print(' Using ' + str(self.ThreadsNum) + ' threads for collecting news ... ')
        with futures.ThreadPoolExecutor(max_workers=self.ThreadsNum) as executor:
            future_to_url = {executor.submit(self.CrawlHistoryCompanyNews,datelst) : \
                             ind for ind, datelst in enumerate(dateLst)}  

    def classifyRealtimeStockNews(self):
        '''Continue crawling and classifying news(articles/documents) every 60s. 
        '''
        today_Date = datetime.datetime.now().strftime('%Y-%m-%d')
        while True:
            print(' * start crawling news from JRJ ... ')
            doc_list = self.CrawlRealtimeCompanyNews(today_Date) #
            print(' * finish crawling ... ')
            if len(doc_list) != 0:
                self.tm.classifyRealtimeStockNews(doc_list)
            time.sleep(60)
