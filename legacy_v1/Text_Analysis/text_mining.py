# -*- coding: UTF-8 -*- 
"""
Created on Sat Jan 20 10:20:33 2018

@author: Damon Li
"""

import os, re, csv, time, warnings, threading
from pymongo import MongoClient
import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix
from bson.objectid import ObjectId
import Text_Analysis.text_processing as tp
from gensim import corpora, utils

from sklearn import svm
from sklearn.ensemble import RandomForestClassifier 
from sklearn.externals import joblib
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import classification_report
import sklearn.exceptions
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore", category=sklearn.exceptions.UndefinedMetricWarning)
warnings.filterwarnings("ignore", category=Warning, module='sklearn')
warnings.filterwarnings("ignore", category=UserWarning, module='gensim')
warnings.filterwarnings("ignore", category=RuntimeWarning, module='gensim')

class TextMining(object):
	'''Text analysis and prediction functions class.

	# Arguments:
		IP: IP address of mongodb database.
		PORT: Port number corresponding to IP.
	'''

	def __init__(self,**kwarg): 
		self.IP = kwarg['IP']
		self.PORT = kwarg['PORT']
		self.ConnDB()
		self.tp = tp.TextProcessing(os.getcwd() + '\\' + 'Chinese_Stop_Words.txt', \
			os.getcwd() + '\\' + 'finance_dict.txt')
		if not os.path.exists(os.getcwd() + '\\' + 'stock_dict_file'):
			os.makedirs(os.getcwd() + '\\' + 'stock_dict_file')
		self.DictPath = os.getcwd() + '\\' + 'stock_dict_file'

	def ConnDB(self):
		'''Connect to the mongodb.
		'''
		self._Conn = MongoClient(self.IP, self.PORT) 

	def extractData(self,dbName,colName,tag_list):
		'''Extract data from specific collection of specific database.

		# Arguments:
			dbName: Name of database.
			colName: Name of collection.
			tag_list: List of tags that need to be extracted.
		'''
		db = self._Conn[dbName]
		collection = db.get_collection(colName)
		data = []
		Dict = {}
		for tag in tag_list:
			exec(tag + " = collection.distinct('" + tag + "')")
			exec("data.append(" + tag + ")")
			exec("Dict.update({'" + tag + "' : np.array(" + tag + ")})")
		dataFrame = pd.DataFrame(Dict,columns=tag_list)
		return dataFrame

	def extractStockCodeFromArticle(self,dbName,colName):
		'''Extract the stocks mentioned by each news(articles/documents).

		# Arguments:
			dbName: Name of database.
			colName: Name of collection.
		'''
		db = self._Conn[dbName]
		collection = db.get_collection(colName)
		idLst = self.extractData(dbName,colName,['_id'])._id
		data = self.extractData("Stock","Basic_Info",['name','code'])
		articles = []
		for _id in idLst:
			if dbName == 'NBD_Stock':
				title = collection.find_one({'_id':ObjectId(_id)})['title']
			else:
				title = collection.find_one({'_id':ObjectId(_id)})['Title']
			article = collection.find_one({'_id':ObjectId(_id)})['Article']
			articles.append(title + ' ' + article)
		token, _, _ = self.tp.genDictionary(articles,saveDict=False)
		j = 0
		for tk in token:
			relevantStockName = []
			relevantStockCode = []
			for k in range(len(tk)):
				if len(tk[k]) >= 3 and tk[k] in list(data.name):
					relevantStockName.append(tk[k]) 
					relevantStockCode.append(list(data[(data.name == tk[k])].code)[0]) 
			if len(relevantStockCode) != 0:
				relevantStockCodeDuplicateRemoval = list(set(relevantStockCode))
				collection.update({"_id":idLst[j]},{"$set":{"relevantStock":\
					' '.join(relevantStockCodeDuplicateRemoval)}})
			# print(' [*] finished ' + str(j+1) + ' ... ')
			j += 1

	def extractStockCodeFromRealtimeNews(self,documents):
		'''Extract stocks mentioined by real-time crawled news(articles/documents), 
			and return the list of corresponding codes.

		# Arguments:
			documents: Real-time crawled news(articles/documents).
		'''
		stock_basic_info = self.extractData("Stock","Basic_Info",['name','code'])
		token_list = self.tp.jieba_tokenize(documents)
		relevant_stock_list = []
		for tokens in token_list:
			relevantStockCode = []
			for tk in tokens:
				if len(tk) >= 3 and tk in list(stock_basic_info.name):
					relevantStockCode.append(list(stock_basic_info[(stock_basic_info.name == tk)].code)[0]) 
			relevant_stock_list.append(list(set(relevantStockCode))) 
		return relevant_stock_list

	def judgeGoodOrBadNews(self,stockCode,date,judgeTerm):
		'''Label the historical news(articles/documents) with 'Bad', 'Good' or 'Neutral'.

		# Arguments:
			stockCode: Code of specific stock.
			date: Date at which released the specific news.
			judgeTerm: Interval after which compare the close price with that at the released date.
		'''
		db = self._Conn['Stock']
		collection = db.get_collection(stockCode)
		dateLst = self.extractData("Stock",stockCode,['date']).date
		days = 0
		CloseLst = []
		for dt in dateLst:
			if dt >= date:
				CloseLst.append(float(collection.find_one({'date':dt})['close']))
				if days >= judgeTerm:
					break
				days += 1
		if CloseLst[-1] > CloseLst[0]:
			character = '利好'
		elif CloseLst[-1] < CloseLst[0]:
			character = '利空'
		else:
			character = '中立'
		return character

	def getNewsOfSpecificStock(self,dbColLst,stockCode,**kwarg):
		'''Get news related to specific stock from historical database.

		# Arguments:
			dbColLst: List of databases and collections, eg: [(db_1,col_1),(db_2,col_2),...,(db_N,col_N)].
			stockCode: Code of specific stock.
			export: List parameters deciding the ways of exporting('csv' or 'database')
					and file path of saving, eg: export=['csv','.\\file'].
		'''
		if kwarg['export'][0] == 'csv':
			with open(kwarg['export'][1] + '\\' + stockCode + '.csv', 'a+', newline='',encoding='utf-8') as file:
				fieldnames = ['date','address','title','article']
				writer = csv.DictWriter(file, fieldnames=fieldnames)
				writer.writeheader()
				for dbName,colName in dbColLst:
					db = self._Conn[dbName]
					collection = db.get_collection(colName)
					idLst = self.extractData(dbName,colName,['_id'])._id
					if dbName == 'Sina_Stock':
						for _id in idLst:
							keys = ' '.join([k for k in collection.find_one({'_id':ObjectId(_id)}).keys()])
							if keys.find('RelevantStock') != -1:
								if collection.find_one({'_id':ObjectId(_id)})['RelevantStock'].find(stockCode) != -1:
									print('     ' + collection.find_one({'_id':ObjectId(_id)})['Title'])
									writer.writerow({'date':collection.find_one({'_id':ObjectId(_id)})['Date'], \
										'address':collection.find_one({'_id':ObjectId(_id)})['Address'], \
										'title':collection.find_one({'_id':ObjectId(_id)})['Title'], \
										'article':collection.find_one({'_id':ObjectId(_id)})['Article']})
					elif dbName == 'NBD':
						for _id in idLst:
							keys = ' '.join([k for k in collection.find_one({'_id':ObjectId(_id)}).keys()])
							if keys.find('relevantStock') != -1:
								if collection.find_one({'_id':ObjectId(_id)})['relevantStock'].find(stockCode) != -1:
									print('     ' + collection.find_one({'_id':ObjectId(_id)})['title'])
									writer.writerow({'date':collection.find_one({'_id':ObjectId(_id)})['date'], \
										'address':collection.find_one({'_id':ObjectId(_id)})['address'], \
										'title':collection.find_one({'_id':ObjectId(_id)})['title'], \
										'article':collection.find_one({'_id':ObjectId(_id)})['Article']})
					print(' [*] extracting ' + stockCode + ' news from ' + dbName + ' database to CSV file successfully ... ')
		elif kwarg['export'][0] == 'database': #new database
			for dbName,colName in dbColLst:
				db = self._Conn[dbName]
				collection = db.get_collection(colName)
				idLst = self.extractData(dbName,colName,['_id'])._id
				if dbName == 'NBD_Stock':
					newdb = self._Conn[kwarg['export'][1]]
					newcollection = newdb.get_collection(kwarg['export'][2])
					for _id in idLst:
						keys = ' '.join([k for k in collection.find_one({'_id':ObjectId(_id)}).keys()])
						if keys.find('relevantStock') != -1:
							if collection.find_one({'_id':ObjectId(_id)})['relevantStock'].find(stockCode) != -1:
								character = self.judgeGoodOrBadNews(stockCode,\
									collection.find_one({'_id':ObjectId(_id)})['date'].split(' ')[0].replace('-',''),kwarg['judgeTerm'])

								# print('     ' + collection.find_one({'_id':ObjectId(_id)})['title'] + '(' + character + ')')

								data = {'Date' : collection.find_one({'_id':ObjectId(_id)})['date'],
										'Address' : collection.find_one({'_id':ObjectId(_id)})['address'],
										'Title' : collection.find_one({'_id':ObjectId(_id)})['title'],
										'Article' : collection.find_one({'_id':ObjectId(_id)})['Article'],
										'Character' : character}
								newcollection.insert_one(data) 
				elif dbName == 'Sina_Stock':
					newdb = self._Conn[kwarg['export'][1]]
					newcollection = newdb.get_collection(kwarg['export'][2])
					for _id in idLst:
						keys = ' '.join([k for k in collection.find_one({'_id':ObjectId(_id)}).keys()])
						if keys.find('RelevantStock') != -1:
							if collection.find_one({'_id':ObjectId(_id)})['RelevantStock'].find(stockCode) != -1:
								character = self.judgeGoodOrBadNews(stockCode,\
									collection.find_one({'_id':ObjectId(_id)})['Date'].split(' ')[0].replace('-',''),kwarg['judgeTerm'])

								# print('     ' + collection.find_one({'_id':ObjectId(_id)})['Title'] + '(' + character + ')')

								data = {'Date' : collection.find_one({'_id':ObjectId(_id)})['Date'],
										'Address' : collection.find_one({'_id':ObjectId(_id)})['Address'],
										'Title' : collection.find_one({'_id':ObjectId(_id)})['Title'],
										'Article' : collection.find_one({'_id':ObjectId(_id)})['Article'],
										'Character' : character}
								newcollection.insert_one(data)
				else:
					newdb = self._Conn[kwarg['export'][1]]
					newcollection = newdb.get_collection(kwarg['export'][2])
					for _id in idLst:
						keys = ' '.join([k for k in collection.find_one({'_id':ObjectId(_id)}).keys()])
						if keys.find('relevantStock') != -1:
							if collection.find_one({'_id':ObjectId(_id)})['relevantStock'].find(stockCode) != -1:
								character = self.judgeGoodOrBadNews(stockCode,\
									collection.find_one({'_id':ObjectId(_id)})['Date'].split(' ')[0].replace('-',''),kwarg['judgeTerm'])

								# print('     ' + collection.find_one({'_id':ObjectId(_id)})['Title'] + '(' + character + ')')

								data = {'Date' : collection.find_one({'_id':ObjectId(_id)})['Date'],
										'Address' : collection.find_one({'_id':ObjectId(_id)})['Address'],
										'Title' : collection.find_one({'_id':ObjectId(_id)})['Title'],
										'Article' : collection.find_one({'_id':ObjectId(_id)})['Article'],
										'Character' : character}
								newcollection.insert_one(data)	
				print(' [' + stockCode + '] ' + dbName + ' has been extracted successfully ... ')

	def classifyHistoryStockNews(self,dbName,stockCode,**kwarg):
		'''Build classifier from historical news(articles/documents) of specific stock.

		# Arguments:
			dbName: Name of database.
			stockCode: Code of specific stock.
			renewDict: Renew the dictionary created by historical news(articles/documents) of
						specific stock or not(bool type).
			modelType: Transformation model type, including 'lsi', 'lda' and 'None', 'None' means TF-IDF mmodel.
			tfDim: The number of topics that will be extracted from each news(articles/documents). 
			renewModel: Re-train the transformation models or not(bool type).
			Classifier: The name of classifier, including 'SVM' and 'RandomForest' so far.
			Params: The parameters of classifier, detail refer to the setting of classifier parameters of scikit-learn module.
		'''
		if kwarg['renewDict']:
			if not os.path.exists(self.DictPath+'\\'+stockCode):
				os.makedirs(self.DictPath+'\\'+stockCode)
			db = self._Conn[dbName]
			collection = db.get_collection(stockCode)
			idLst = self.extractData(dbName,stockCode,['_id'])._id
			articles = []
			characters = []
			for _id in idLst:
				articles.append(collection.find_one({'_id':ObjectId(_id)})['Article'])
				if collection.find_one({'_id':ObjectId(_id)})['Character'] == "利好":
					characters.append(1)
				elif collection.find_one({'_id':ObjectId(_id)})['Character'] == "利空":
					characters.append(-1)
				else:
					characters.append(0)
			self.tp.genDictionary(articles,saveDict=True,saveDictPath=self.DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict',\
				saveBowvec=True,saveBowvecPath=self.DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm',returnValue=False)
			print(' [*] renew the dictionary and bow-vector successfully ... ')
		elif not os.path.exists(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict') \
		or not os.path.exists(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm'):
			if not os.path.exists(self.DictPath+'\\'+stockCode):
				os.makedirs(self.DictPath+'\\'+stockCode)
			db = self._Conn[dbName]
			collection = db.get_collection(stockCode)
			idLst = self.extractData(dbName,stockCode,['_id'])._id
			articles = []
			characters = []
			for _id in idLst:
				articles.append(collection.find_one({'_id':ObjectId(_id)})['Article'])
				if collection.find_one({'_id':ObjectId(_id)})['Character'] == "利好":
					characters.append(1)
				elif collection.find_one({'_id':ObjectId(_id)})['Character'] == "利空":
					characters.append(-1)
				else:
					characters.append(0)
			self.tp.genDictionary(articles,saveDict=True,saveDictPath=self.DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict',\
				saveBowvec=True,saveBowvecPath=self.DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm',returnValue=False)
			print(' [*] generate and save the dictionary and bow-vector successfully ... ')
		else:
			db = self._Conn[dbName]
			collection = db.get_collection(stockCode)
			idLst = self.extractData(dbName,stockCode,['_id'])._id
			characters = []
			for _id in idLst:
				if collection.find_one({'_id':ObjectId(_id)})['Character'] == "利好":
					characters.append(1)
				elif collection.find_one({'_id':ObjectId(_id)})['Character'] == "利空":
					characters.append(-1)
				else:
					characters.append(0)
		dictionary = corpora.Dictionary.load(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict')
		bowvec = corpora.MmCorpus(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm')
		print(' [*] load dictionary and bow-vector successfully ... ')
		_, modelVec = self.tp.CallTransformationModel(dictionary,bowvec,modelType=kwarg['modelType'],\
			tfDim=kwarg['tfDim'],renewModel=kwarg['renewModel'],modelPath=self.DictPath+'\\'+stockCode+'\\')
		CSRMatrix = self.ConvertToCSRMatrix(modelVec)
		train_X, train_Y, test_X, test_Y = self.genTrainingSet(CSRMatrix,characters)
		if kwarg['Classifier'] == 'SVM':
			self.SVMClassifier(train_X,train_Y,test_X,test_Y,kwarg['Params'],['precision'],stockCode)
		if kwarg['Classifier'] == 'RandomForest':
			self.RdForestClassifier(train_X,train_Y,test_X,test_Y,kwarg['Params'],['precision'],stockCode)
		return self._precise

	def classifyRealtimeStockNews(self,doc_list):
		'''Classify real-time news(articles/documents) of specific stock.

		#Arguments:
			doc_list: List of real-time news(articles/documents) crawled from specific websites.
		'''
		print(' * extract relevant stock codes from latest crawled news ... ')
		relevant_stock_list = self.extractStockCodeFromRealtimeNews(doc_list)
		if len(relevant_stock_list) != 0:
			tfDim = 200
			for i, code_list in enumerate(relevant_stock_list):
				for code in code_list:

					print(' * load SVM parameters (gamma & C) ... ')
					Params_svm = {'kernel': ['rbf'], 'gamma': [10, 20, 50, 100, 150, 200], \
						'C': [10, 15, 20, 30, 50, 100]}

					print(' * use historical news to build SVM model of ' + code + ' ... ')
					self.classifyHistoryStockNews("Stock_News",code,modelType='lda',tfDim=tfDim,renewDict=False,\
							renewModel=False,Classifier='SVM',Params=Params_svm) #code="600740"

					print(' * load historical dictionary of ' + code + ' ...')
					dictionary = corpora.Dictionary.load(os.getcwd() + '\\' + 'stock_dict_file\\' + code + '\\' + code + '_dict.dict')
					
					print(' * tokenize latest crawled news ... ')
					token = self.tp.jieba_tokenize(doc_list)

					print(' * create bow-vector of latest news of ' + code + ' ... ')
					bowvec_doc = [dictionary.doc2bow(text) for text in token]
					
					print(' * load bow-vector of historical news of ' + code + ' ... ')
					bowvec_all = list(corpora.MmCorpus(os.getcwd() + '\\' + 'stock_dict_file\\' + code + '\\' + code + '_bowvec.mm'))
					
					print(' * extend latest bow-vector to historical bow-vector of ' + code + ' ... ')
					bowvec_all.extend(bowvec_doc)
					
					print(' * create new lda model of ' + code + ' ... ')
					_, NewmodelVec = self.tp.CallTransformationModel(dictionary,bowvec_all,modelType='lda',\
									tfDim=200,renewModel=False,modelPath=os.getcwd() + '\\' + 'stock_dict_file\\' + code + '\\')
					
					print(' * convert latest lda vector to CSR matrix of ' + code + ' ... ')
					NewCSRMatrix = self.ConvertToCSRMatrix(NewmodelVec)
					
					print(' * load SVM model of ' + code + ' ... ')
					clf = joblib.load(os.getcwd() + '\\' + 'stock_dict_file\\' + code + '\\' + code + '_svm.pkl') 
					
					print(' * predicting ... ')
					if clf.predict(NewCSRMatrix[i-2,:])[0] == 1:
						print('   《' + doc_list[i].split(' ')[0] + "》" + '对' + code + '是利好消息 ...')
					elif clf.predict(NewCSRMatrix[i-2,:])[0] == -1:
						print('   《' + doc_list[i].split(' ')[0] + "》" + '对' + code + '是利空消息 ...')
					else:
						print('   《' + doc_list[i].split(' ')[0] + "》" + '对' + code + '是中立消息 ...')
		else:
			print(' * not any relevant stock ... ')

	def SVMClassifier(self,train_X,train_Y,test_X,test_Y,tuned_parameters,scores,stockCode):
		'''SVM Classifier.

		# Arguments:
			train_X: Features train data. 
			train_Y: Labels train data.
			test_X: Features train data.
			test_Y: Labels train data.
			tuned_parameters: The parameters of classifier, refer to the setting of classifier parameters of scikit-learn module.
			scores: Targets of optimization, detail refer to optimal targets setting of scikit-learn module.
			stockCode: Code of specific stock.
		'''
		for score in scores:
			if not os.path.exists(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_svm.pkl'):
				clf = GridSearchCV(svm.SVC(), tuned_parameters, cv=5, scoring='%s_weighted' % score) # 构造这个GridSearch的分类器,5-fold
				clf.fit(train_X, train_Y) # 只在训练集上面做k-fold,然后返回最优的模型参数
				joblib.dump(clf, self.DictPath+'\\'+stockCode+'\\'+stockCode+'_svm.pkl')
				print(clf.best_params_) # 输出最优的模型参数
			else:
				clf = joblib.load(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_svm.pkl') 
			# for params, mean_score, scores in clf.grid_scores_:
			# 	print("%0.3f (+/-%0.03f) for %r" % (mean_score, scores.std() * 2, params))
			train_pred = clf.predict(train_X) 
			test_pred = clf.predict(test_X) # 在测试集上测试最优的模型的泛化能力.
			print(classification_report(test_Y, test_pred))

		precise_train = 0
		for k in range(len(train_pred)):
			if train_pred[k] == train_Y[k]:
				precise_train += 1
		precise_test = 0
		for k in range(len(test_pred)):
			if test_pred[k] == test_Y[k]:
				precise_test += 1
		print(' [*] train_pred:', precise_train/len(train_Y), ', test_pred:', precise_test/len(test_pred))
		print(' ' + '-' * 50)
		self._precise = precise_test/len(test_pred)

	def RdForestClassifier(self,train_X,train_Y,test_X,test_Y,tuned_parameters,scores,stockCode):
		'''Random Forest Classifier.

		# Arguments:
			train_X: Features train data. 
			train_Y: Labels train data.
			test_X: Features train data.
			test_Y: Labels train data.
			tuned_parameters: The parameters of classifier, refer to the setting of classifier parameters of scikit-learn module.
			scores: Targets of optimization, detail refer to optimal targets setting of scikit-learn module.
			stockCode: Code of specific stock.
		'''
		for score in scores:
			if not os.path.exists(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_rdf.pkl'):
				clf = GridSearchCV(RandomForestClassifier(random_state=14), tuned_parameters, cv=5, scoring='%s_weighted' % score) # 构造这个GridSearch的分类器,5-fold
				clf.fit(train_X, train_Y) # 只在训练集上面做k-fold,然后返回最优的模型参数
				joblib.dump(clf, self.DictPath+'\\'+stockCode+'\\'+stockCode+'_rdf.pkl')
				print(clf.best_params_) # 输出最优的模型参数
			else:
				clf = joblib.load(self.DictPath+'\\'+stockCode+'\\'+stockCode+'_rdf.pkl') 
			# for params, mean_score, scores in clf.grid_scores_:
			# 	print("%0.3f (+/-%0.03f) for %r" % (mean_score, scores.std() * 2, params))
			train_pred = clf.predict(train_X) 
			test_pred = clf.predict(test_X) # 在测试集上测试最优的模型的泛化能力.
			print(classification_report(test_Y, test_pred))
		precise_train = 0
		for k in range(len(train_pred)):
			if train_pred[k] == train_Y[k]:
				precise_train += 1
		precise_test = 0
		for k in range(len(test_pred)):
			if test_pred[k] == test_Y[k]:
				precise_test += 1
		print(' [*] train_pred:', precise_train/len(train_Y), ', test_pred:', precise_test/len(test_pred))
		print(' ' + '-' * 50)
		self._precise = precise_test/len(test_pred)

	def ConvertToCSRMatrix(self,modelVec):
		'''Convert LDA(LSI) model vector to CSR sparse matrix, that could be accepted by Scipy and Numpy.
		
		# Arguments:
			modelVec: Transformation model vector, such as LDA model vector, tfidf model vector or lsi model vector.
		'''
		data = []
		rows = []
		cols = []
		self._line_count = 0
		for line in modelVec:  
			for elem in line:
				rows.append(self._line_count)
				cols.append(elem[0])
				data.append(elem[1])
			self._line_count += 1
		sparse_matrix = csr_matrix((data,(rows,cols))) 
		matrix = sparse_matrix.toarray() 
		return matrix

	def genTrainingSet(self,X,Y):
		'''Generate training data set.

		# Arguments:
			X: Feature set.
			Y: Label set.
		'''
		rarray=np.random.random(size=self._line_count)
		train_X = []
		train_Y = []
		test_X = []
		test_Y = []
		for i in range(self._line_count):
			if rarray[i]<0.8:
				train_X.append(X[i,:])
				train_Y.append(Y[i])
			else:
				test_X.append(X[i,:])
				test_Y.append(Y[i])
		return train_X,train_Y,test_X,test_Y
