from pymongo import MongoClient
import pandas as pd


class Database(object):

	def __init__(self, ip="localhost", port=27017):
		self.ip = ip
		self.port = port
		self.conn = MongoClient(self.ip, self.port)

	def connect_database(self, database_name):
		return self.conn[database_name]

	def get_collection(self, database_name, collection_name):
		return self.connect_database(database_name).get_collection(collection_name)

	def insert_data(self, database_name, collection_name, data_dict):
		database = self.conn[database_name]
		collection = database.get_collection(collection_name)
		collection.insert_one(data_dict)

	def update_row(self, database_name, collection_name, query, new_values):
		assert isinstance(query, dict)
		assert isinstance(new_values, dict)
		database = self.conn[database_name]
		collection = database.get_collection(collection_name)
		collection.update_one(query, {"$set": new_values})

	def get_data(self, database_name, collection_name, max_data_request=None, query=None, keys=None):
		# e.g.:
		# ExampleObj = Database()
		# ExampleObj.get_data("finnewshunter", "nbd", query={"Date": {"$regex": "2014"}}, keys=["Url", "Title"])
		database = self.conn[database_name]
		collection = database.get_collection(collection_name)
		if query:
			assert isinstance(query, dict)
		else:
			query = {}
		if keys:
			assert isinstance(keys, list)
		else:
			keys = []
		if max_data_request:
			assert isinstance(max_data_request, int)
		else:
			max_data_request = float("inf")
		try:
			if len(keys) != 0:
				_dict = {_key: [] for _key in keys}
				data = collection.find(query) if len(query) != 0 else collection.find()
				for _id, row in enumerate(data):
					if _id + 1 <= max_data_request:
						for _key in keys:
							_dict[_key].append(row[_key])
					else:
						break
			else:
				# data = collection.find()
				data = collection.find(query) if len(query) != 0 else collection.find()
				data_keys = list(
					next(data).keys())  # ['_id', 'Date', 'PageId', 'Url', 'Title', 'Article', 'RelevantStockCodes']
				_dict = {_key: [] for _key in data_keys}
				for _id, row in enumerate(collection.find(query) if len(query) != 0 else collection.find()):
					if _id + 1 <= max_data_request:
						for _key in data_keys:
							_dict[_key].append(row[_key])
					else:
						break
			return pd.DataFrame(_dict)
		except Exception:
			return None

	def drop_db(self, database):
		self.conn.drop_database(database)


'''
from database import Database

ExampleObj = Database()
db = ExampleObj.connect_database("cnstock")
col = ExampleObj.create_col(db, "cnstock_col")
ExampleObj.insert_data(col, {'name': 'sena', "id": 136})
ExampleObj.drop_db(db)
'''

