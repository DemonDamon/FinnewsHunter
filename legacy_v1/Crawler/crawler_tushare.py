import pymongo
import tushare as ts
import datetime
import time
import math
import traceback

class CrawlStockData(object):
	def __init__(self,**kwarg):
		self.IP = kwarg['IP']
		self.PORT = kwarg['PORT']
		self.ConnDB()
		self.stockDailyPath = 'D:\\stock_daliy'

	def ConnDB(self):
		self._Conn = pymongo.MongoClient(self.IP, self.PORT) 

	def extractData(self,dbName,colName,tag_list):
		db = self._Conn[dbName]
		collection = db.get_collection(colName)
		data = []
		for tag in tag_list:
			exec(tag + " = collection.distinct('" + tag + "')")
			exec("data.append(" + tag + ")")
		return data

	def getStockBasicFromTushare(self,dbName,colName):
		db = self._Conn[dbName]
		collection = db.get_collection(colName)
		stock_basic_info = ts.get_stock_basics()
		for i in range(len(stock_basic_info)):
			data = {stock_basic_info.index.name : stock_basic_info.index[i]}
			data.update({'name' : stock_basic_info['name'][i]})
			data.update({'industry' : stock_basic_info['industry'][i]})
			data.update({'area' : stock_basic_info['area'][i]})
			data.update({'pe' : stock_basic_info['pe'][i]})
			data.update({'outstanding' : stock_basic_info['outstanding'][i]})
			data.update({'totals' : stock_basic_info['totals'][i]})
			data.update({'totalAssets' : stock_basic_info['totalAssets'][i]})
			data.update({'liquidAssets' : stock_basic_info['liquidAssets'][i]})
			data.update({'fixedAssets' : stock_basic_info['fixedAssets'][i]})
			data.update({'reserved' : stock_basic_info['reserved'][i]})
			data.update({'reservedPerShare' : stock_basic_info['reservedPerShare'][i]})
			data.update({'esp' : stock_basic_info['esp'][i]})
			data.update({'bvps' : stock_basic_info['bvps'][i]})
			data.update({'pb' : stock_basic_info['pb'][i]})
			data.update({'undp' : stock_basic_info['undp'][i]})
			data.update({'perundp' : stock_basic_info['perundp'][i]})
			data.update({'rev' : stock_basic_info['rev'][i]})
			data.update({'profit' : stock_basic_info['profit'][i]})
			data.update({'gpr' : stock_basic_info['gpr'][i]})
			data.update({'npr' : stock_basic_info['npr'][i]})
			data.update({'holders' : stock_basic_info['holders'][i]})
			#detail = dict(zip(stock_basic_info.columns, [stock_basic_info[j][i] for j in stock_basic_info.columns]))
			collection.insert_one(data)

	def renewStockBasic(self):
		pass

	def getStockTickHistory(self,dbName,stockCode):
		try:
			db = self._Conn[dbName]
			collection = db.get_collection(stockCode)
			date = self.extractData("NBD","nbd_news_company",['date'])[0]
			begin_date = min(date).split(' ')[0]
			date_list = self.getCalendar(begin_date)
			for dt in date_list:
				tickDataOfEachDate = ts.get_tick_data(stockCode,date=dt)
				if not math.isnan(tickDataOfEachDate['price'][0]): #exist data at that day
					data = {}
					for i in range(len(tickDataOfEachDate)-1,-1,-1):
						data.update({'date' : dt})
						data.update({'time' : tickDataOfEachDate['time'][i]})
						data.update({'price' : tickDataOfEachDate['price'][i]})
						data.update({'change' : tickDataOfEachDate['change'][i]})
						data.update({'volume' : int(tickDataOfEachDate['volume'][i])})
						data.update({'amount' : int(tickDataOfEachDate['amount'][i])})
						data.update({'type' : tickDataOfEachDate['type'][i]})
						collection.insert_one(data)
						data = {}
				print(dt + ' crawl finished ... ')
		except Exception:
			traceback.print_exc()

	def getStockDayHistory(self,dbName,stockCode):
		db = self._Conn[dbName]
		collection = db.get_collection(stockCode)
		Path = self.stockDailyPath + '\\' + stockCode + '.txt'
		data = []
		for row in open(Path,'r'):
			line = row.split()
			data.append(line)
		Dict = {}
		for i in range(len(data)):
			if len(data[i]) > 1:
				Dict.update({'date' : data[i][0]})
				Dict.update({'open' : data[i][1]})
				Dict.update({'high' : data[i][2]})
				Dict.update({'low' : data[i][3]})
				Dict.update({'close' : data[i][4]})
				Dict.update({'volume' : data[i][5]})
				Dict.update({'turnover' : data[i][6]})
				collection.insert_one(Dict)
				Dict = {}

	def getCalendar(self,begin_date):  
		date_list = []  
		begin_date = datetime.datetime.strptime(begin_date, "%Y-%m-%d")  
		end_date = datetime.datetime.strptime(time.strftime('%Y-%m-%d',time.localtime(time.time())), "%Y-%m-%d")  
		while begin_date <= end_date:  
			date_str = begin_date.strftime("%Y-%m-%d")  
			date_list.append(date_str)  
			begin_date += datetime.timedelta(days=1)  
		return date_list

	def isUnique(self, List):  
		# write your code here  
		n = len(List)  
		for i in range(n):  
			if List.count(List[i]) != 1: #判断单个字符串a[i]出现次数  
				return False  
				#break  
		return True 

	def getStockTickRealtime(self):
		pass


