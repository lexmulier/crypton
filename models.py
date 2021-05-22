from pymongo import MongoClient
from sshtunnel import SSHTunnelForwarder


class MongoDB(object):
    def __init__(self, database_name="crypton", host='localhost', port=27017):
        self._connection = MongoClient(host=host, port=port)
        self.client = self._connection[database_name]


class MongoDBTunnel(object):
    def __init__(self, remote_ip, ssh_username, ssh_private_key_file):
        self.tunnel = SSHTunnelForwarder(
            remote_ip,
            ssh_username=ssh_username,
            ssh_pkey=ssh_private_key_file,
            remote_bind_address=('127.0.0.1', 27017)
        )

    def start(self):
        self.tunnel.start()
        return MongoDB(host="127.0.0.1", port=self.tunnel.local_bind_port)

    def stop(self):
        self.tunnel.stop()


db = MongoDB()

