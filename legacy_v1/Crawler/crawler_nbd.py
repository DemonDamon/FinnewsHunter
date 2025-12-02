# -*- coding: utf-8 -*-
"""
Created on Tue Jan 23 17:19:50 2018

@author: Damon Li
"""

import re, os, time, requests
from bs4 import BeautifulSoup
import pymongo, threading, traceback

import gevent
from gevent import monkey,pool
monkey.patch_all()


class WebCrawlFromNBD(object):
    '''Crawl company news from 'http://stocks.nbd.com.cn/columns/275' website.

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
        self.totalPages = arg[0] #totalPages
        self.Range = arg[1] #Range
        self.ThreadsNum = kwarg['ThreadsNum']
        self.dbName = kwarg['dbName']
        self.colName = kwarg['collectionName']
        self.IP = kwarg['IP']
        self.PORT = kwarg['PORT']
        self.url_lst_withoutArticles = []
        self.title_lst_withoutArticles = []
        self.url_lst_withoutNews = []
        self.CrawledUrlsID = []
        self.filePath = os.path.dirname(os.path.realpath(__file__))

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
            if 'class' in span.attrs and span.text and span['class'] == ['time']:
                    string = span.text.split()
                    for dt in string:
                        if dt.find('-') != -1:
                            date += dt + ' '
                        elif dt.find(':') != -1:
                            date += dt
                    break

        for paragraph in part:
            chnstatus = self.countchn(str(paragraph))
            possible = chnstatus[1]
            if possible > 0.5:
               article += str(paragraph)

        while article.find('<') != -1 and article.find('>') != -1:
              string = article[article.find('<'):article.find('>')+1]
              article = article.replace(string,'')
        while article.find('\u3000') != -1:
              article = article.replace('\u3000','')

        article = ' '.join(re.split(' +|\n+', article)).strip() 

        return article, date

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

    def ReCrawlNews(self,url_list):
        '''Continue crawling pages without any return.

        # Arguments:
          url_list: List of web pages that without any values.
        '''
        try:
          nums = 1
          ulst = []
          while url_list != []:
             ulst.append(url_list[0])
             print(' <Re-Crawl News> ', url_list[0])
             if nums > 10:
                print(' <!> wait 1s before request url again ...')
                time.sleep(1)
                nums = 1
             resp = requests.get(url_list[0])
             resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
             bs = BeautifulSoup(resp.text, "lxml")
             a_list = bs.find_all('a')
             if a_list != []:
               for a in a_list:
                   if 'click-statistic' in a.attrs and a.string \
                   and a['click-statistic'].find('Article_') != -1 \
                   and a['href'].find('http://www.nbd.com.cn/articles/') != -1:
                       article, date = self.getUrlInfo(a['href'])
                       if date == '' or article == '':
                          self.url_lst_withoutArticles.append(a['href'])
                          self.title_lst_withoutArticles.append(a.string)
                       elif date != '' and article != '':
                           data = {'date' : date,
                                   'address' : a['href'],
                                   'title' : a.string,
                                   'Article' : article}
                           self.collection.insert_one(data)
                           self.CrawledUrlsID.append(int(url_list[0].split('/')[-1]))
               url_list.remove(url_list[0])
             if len(ulst) >= 2 and ulst[-1] == ulst[-2]:
                nums += 1
          return self.url_lst_withoutArticles, self.title_lst_withoutArticles
        except Exception:
            traceback.print_exc()

    def ReCrawlArticles(self,url_list,title_list):
        '''Continue crawling urls without main information return.

        # Arguments:
          url_list: List of urls without getting any articles(main body).
          title_list: List of urls without crawling any titles.
        '''
        nums = 1
        ulst = []
        while url_list != []:
            ulst.append(url_list[0])
            print(' <Re-Crawl Articles> ', url_list[0])
            if nums > 10:
              print(' <!> wait 1s before request url again ...')
              time.sleep(1)
              nums = 1
            article, date = self.getUrlInfo(url_list[0])
            if date != '' and article != '':
               data = {'date' : date,
                       'address' : url_list[0],
                       'title' : title_list[0],
                       'Article' : article}
               print(' remove ' + url_list[0] + ' successfully ... ')
               url_list.remove(url_list[0])
               title_list.remove(title_list[0])
               self.collection.insert_one(data)
            if len(ulst) >= 2 and ulst[-1] == ulst[-2]:
               nums += 1

    def CrawlCompanyNews(self,startPage,endPage):
        '''Crawl historical company news 
        '''
        self.ConnDB()
        AddressLst = self.extractData(['address'])[0]
        if AddressLst == []:
          urls = []
          url_Part = 'http://stocks.nbd.com.cn/columns/275/page/' 
          for pageId in range(startPage,endPage+1):
              urls.append(url_Part + str(pageId))
          for url in urls:
              print(url)
              resp = requests.get(url)
              resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
              bs = BeautifulSoup(resp.text, "lxml")
              a_list = bs.find_all('a')
              if a_list == []:
                self.url_lst_withoutNews.append(url)
              else:
                for a in a_list:
                    if 'click-statistic' in a.attrs and a.string \
                    and a['click-statistic'].find('Article_') != -1 \
                    and a['href'].find('http://www.nbd.com.cn/articles/') != -1:
                        article, date = self.getUrlInfo(a['href'])
                        if date == '' or article == '':
                           self.url_lst_withoutArticles.append(a['href'])
                           self.title_lst_withoutArticles.append(a.string)
                        elif date != '' and article != '':
                            data = {'date' : date,
                                    'address' : a['href'],
                                    'title' : a.string,
                                    'Article' : article}
                            self.collection.insert_one(data)
                            self.CrawledUrlsID.append(int(url.split('/')[-1]))
        else:
          urls = []
          url_Part = 'http://stocks.nbd.com.cn/columns/275/page/' 
          for pageId in range(startPage,endPage+1):
              urls.append(url_Part + str(pageId))
          for url in urls:
              print(' <Re-Crawl url> ', url)
              resp = requests.get(url)
              resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
              bs = BeautifulSoup(resp.text, "lxml")
              a_list = bs.find_all('a')
              if a_list == []:
                self.url_lst_withoutNews.append(url)
              else:
                for a in a_list:
                    if 'click-statistic' in a.attrs and a.string \
                    and a['click-statistic'].find('Article_') != -1 \
                    and a['href'].find('http://www.nbd.com.cn/articles/') != -1:
                        if a['href'] not in AddressLst:
                            article, date = self.getUrlInfo(a['href'])
                            if date == '' or article == '':
                               self.url_lst_withoutArticles.append(a['href'])
                               self.title_lst_withoutArticles.append(a.string)
                            elif date != '' and article != '':
                                data = {'date' : date,
                                        'address' : a['href'],
                                        'title' : a.string,
                                        'Article' : article}
                                self.collection.insert_one(data)
                                self.CrawledUrlsID.append(int(url.split('/')[-1]))

    def ConnDB(self):
        '''Connect mongodb.
        '''
        client = pymongo.MongoClient(self.IP, self.PORT)
        mydb = client[self.dbName]
        self.collection = mydb.get_collection(self.colName)

    def extractData(self,tag_list):
        '''Extract column data with tag in 'tag_list' to the list.
        '''
        data = []
        for tag in tag_list:
            exec(tag + " = self.collection.distinct('" + tag + "')")
            exec("data.append(" + tag + ")")
        return data

    def single_run(self):
        '''Single threading running.
        '''
        page_ranges_lst = self.GenPagesLst()
        for ind, page_range in enumerate(page_ranges_lst):
            self.CrawlCompanyNews(page_range[0],page_range[1]) 
        return self.url_lst_withoutNews

    def multi_threads_run(self):
        '''Multi-threading running.
        '''
        page_ranges_lst = self.GenPagesLst()
        th_lst = []
        for page_range in page_ranges_lst:
            thread = threading.Thread(target=self.CrawlCompanyNews,\
                                      args=(page_range[0],page_range[1]))
            th_lst.append(thread)
        for thread in th_lst:
            thread.start()
        for thread in th_lst:
            thread.join()
        return self.url_lst_withoutNews

    def coroutine_run(self):
        '''Coroutines running.
        '''
        jobs = []
        page_ranges_lst = self.GenPagesLst()
        for page_range in page_ranges_lst:
            jobs.append(gevent.spawn(self.CrawlCompanyNews,page_range[0],page_range[1]))
        gevent.joinall(jobs) 
        return self.url_lst_withoutNews