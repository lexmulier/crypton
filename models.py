from pymongo import MongoClient


class MongoDB(object):

    def __init__(self, database_name="crypton", host='localhost', port=27017):
        self._connection = MongoClient(host=host, port=port)
        self.client = self._connection[database_name]


db = MongoDB()
