#cassandra
from cassandra_client.protocol.genpy.cassandra import Cassandra
from cassandra_client.protocol.genpy.cassandra.ttypes import *
from cassandra_client import cassandra_api
from thrift_client import thrift_client
from Queue import Queue
import conf

from datetime import datetime
import json
import web
urls = (
    #/time_line?category='latency'&key='add_user'&type=1&start='0'&finish=''&reversed=0&count=1000&p='m'
    '/time_line', 'time_line',
    #/event?category='frequency&key='stats:add_user:host1'&start='0'&finish=''&reversed=0&count=1000&p='m'
    '/event', 'event',
    #/stats?category='latency'&count=1000
    '/stats', 'stats',
)
app = web.application(urls, globals())

TIMELINE_KEYSPACE = 'timeline_stats'
EVENT_KEYSPACE = 'event_stats'
SERVERS = conf.SERVERS

TYPE2STR = {
    0:'PT_MIN',
    1:'PT_MAX',
    2:'PT_AVG',
    3:'Q0',
    4:'Q1',
    5:'Q2',
    6:'P9',
}

def create_cassandra_client(keyspace, servers):
    client = thrift_client.ThriftClient(client_class=Cassandra.Client,
                    servers=servers)
    return cassandra_api.CassandraAPI(handle=client, keyspace=keyspace)

def get_daystr():
    now = datetime.now()
    return '%d-%d-%d' % (now.year, now.month, now.day)

def get_store_pk(category, key):
    daystr = get_daystr()
    return daystr + ':' + category + ':' + key


class ReqProxy(object):
    def __init__(self, conn_num=10):
        self._eq = Queue(maxsize=conn_num)
        for i in xrange(conn_num):
            self._eq.put(create_cassandra_client(keyspace=EVENT_KEYSPACE, servers=SERVERS))
        self._tq = Queue(maxsize=conn_num)
        for i in xrange(conn_num):
            self._tq.put(create_cassandra_client(keyspace=TIMELINE_KEYSPACE, servers=SERVERS))

    def timeline_select_slice(self, pk, cf, start, finish, reversed, count):
        try:
            conn = self._tq.get(block=True)
            return self._select_slice(conn, pk, cf, start, finish, reversed, count)
        finally:
            self._tq.put(conn)

    def event_select_slice(self, pk, cf, start, finish, reversed, count):
        try:
            conn = self._eq.get(block=True)
            return self._select_slice(conn, pk, cf, start, finish, reversed, count)
        finally:
            self._eq.put(conn)

    def timeline_get_ranges(self, cf, columns, start_key, end_key, count):
        try:
            conn = self._tq.get(block=True)
            return conn.get_range(cf=cf, columns=columns, start_key=start_key, end_key=end_key, count=count)
        finally:
            self._tq.put(conn)

    def event_get_ranges(self, cf, columns, start_key, end_key, count):
        try:
            conn = self._eq.get(block=True)
            return conn.get_range(cf=cf, columns=columns, start_key=start_key, end_key=end_key, count=count)
        finally:
            self._eq.put(conn)

    def _select_slice(self, conn, pk, cf, start, finish, reversed, count):
        return conn.select_slice(pk=pk, cf=cf, start=start, finish=finish, reversed=reversed, count=count)

req_proxy = ReqProxy()

class time_line:
    def GET(self):
        wi = web.input()
        category = wi.category
        key = wi.key
        cf = wi.type
        start = wi.start
        finish = wi.finish
        reversed = wi.reversed
        count = int(wi.count)
        p = wi.p
        if p == 'm':
            pk = get_store_pk(category, key)
        else:
            pk = category + ':' + key
        slice = req_proxy.timeline_select_slice(pk=pk, cf=cf, start=start, finish=finish, reversed=int(reversed), count=count)
        l = []
        for item in slice:
            l.append((item.column.name, item.column.value))
        j = {'slice':l, 't':TYPE2STR[int(cf)]}
        return json.dumps(j)

class event:
    def GET(self):
        wi = web.input()
        category = wi.category
        key = wi.key
        start = wi.start
        finish = wi.finish
        reversed = wi.reversed
        count = int(wi.count)
        p = wi.p
        if p == 'm':
            pk = get_store_pk(category, key)
        else:
            pk = category + ':' + key
        slice = req_proxy.event_select_slice(pk=pk, cf=p, start=start, finish=finish, reversed=int(reversed), count=count)
        l = []
        for item in slice:
            l.append((item.counter_column.name, item.counter_column.value))
        j = {'slice':l}
        return json.dumps(j)

class stats:
    def GET(self):
        wi = web.input()
        category = wi.category
        start_key = ''
        end_key = ''
        count = int(wi.count)
        if category == 'frequency':
            slice = req_proxy.event_get_ranges(cf='Y', columns=[], start_key=start_key, end_key=end_key, count=count)
        elif category == 'latency':
            slice = req_proxy.timeline_get_ranges(cf='0', columns=[], start_key=start_key, end_key=end_key, count=count)
        l = []
        daystr = get_daystr()
        for item in slice:
            l.append(item.key.replace(daystr+':', ''))
        j = {'slice': l}
        return json.dumps(j)

if __name__ == "__main__":
    app.run()
