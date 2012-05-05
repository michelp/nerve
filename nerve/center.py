import collections
import gevent
import logging
import sys
import zmq.green as zmq
from cPickle import dumps, loads
from sqlalchemy.sql import text
from uuid import uuid1

from . import db


logger = logging.getLogger(__name__)


class Center(object):
    """
    Process event collection.
    """
    synced = False

    def __init__(self,
                 session,
                 name,
                 endpoint,
                 controlpoint,
                 syncpoint,
                 ring,
                 logfile):

        self.session = session
        self.name = name
        self.endpoint = endpoint
        self.controlpoint = controlpoint
        self.syncpoint = syncpoint
        self.logfile = logfile
        self.ring = ring

        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)
        self.router.bind(self.endpoint)
        self.control = self.context.socket(zmq.ROUTER)
        self.control.bind(self.controlpoint)
        self.syncin = self.context.socket(zmq.SUB)
        self.syncin.setsockopt(zmq.SUBSCRIBE, '')
        self.syncin.setsockopt(zmq.SUBSCRIBE, name)
        self.syncin.bind(self.syncpoint)
        self.syncout = self.context.socket(zmq.PUB)

        if ring:
            for peer in ring.split('.'):
                self.syncout.connect(peer)

    def start(self):
        gevent.spawn(self._read_syncin)
        gevent.spawn(self._read_router)
        controller = gevent.spawn(self._read_control)
        controller.join()

    def _log(self, sender, cmd, data):
        self.logfile.write(repr([sender, cmd, data])+'\n')
        self.logfile.flush()

    def _update_rows(self, data):
        for row in data:
            p = db.Process(**row)
            self.session.merge(p)
        self.session.commit()

    def _read_syncin(self):
        gevent.sleep(.1)
        self.syncout.send('sync')
        while True:
            data = None
            msg = self.syncin.recv()
            try:
                if msg.startswith(self.name):
                    data = loads(msg[len(self.name):])
                else:
                    data = ([loads(data)])
            except Exception:
                print 'error syncing'
                continue
            if data:
                print 'syncing ', data
                self._update_rows(data)

    def _read_router(self):
        while True:
            try:
                sender, _, typ, cmd, raw = self.router.recv_multipart()
                data = loads(raw)
            except ValueError:
                continue
            self._log(sender, cmd, data)
            if typ == 'process':
                if cmd == 'ping' or cmd == 'state':
                    self._update_rows([data])
                    self.router.send_multipart([sender, '', 'center', self.name])

                elif cmd == 'return' or cmd == 'signal':
                    query = self.session.query(db.Process)
                    query.filter(db.Process.uuid==data[0]).delete()
                    self.session.commit()
            elif typ == 'center':
                pass

    def _read_control(self):
        while True:
            sender, _, cmd, data = self.control.recv_multipart()
            response = None
            try:
                if cmd == 'query':
                    select, where = loads(data)
                    query = 'SELECT ' + select + ' FROM process'
                    if where:
                        query += ' WHERE ' + where

                    result = db.engine.execute(text(query))
                    response = (result.keys(), list(result))
                else:
                    raise NameError, 'no such command %s' % cmd
            except Exception, e:
                response = e
            finally:
                self.control.send_multipart([sender, '', dumps(response)])

    def run(self):
        return gevent.spawn(self.start)


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

    parser.add_option('-c', '--controlpoint', dest='controlpoint', default='ipc://control.sock',
                      help='Specify zerovisor control endpoint.')

    parser.add_option('-s', '--syncpoint', dest='syncpoint', default='ipc://syncpoint.sock',
                      help='Endpoint for receiving sync data.')

    parser.add_option('-n', '--name', dest='name', default=uuid1().hex,
                      help="Center name.  Default is a random UUID.")

    parser.add_option('-R', '--ring', dest='ring', default=None,
                      help="Comma separated list of peer center endpoints.")

    parser.add_option('-l', '--logfile', dest='logfile', default='zerovisor.log',
                      help='Specify the log file.')

    parser.add_option('-d', '--debug', action='store_true', dest='debug', default=False,
                      help='Debug on unhandled error.')

    parser.add_option('-E', '--echo-sql', action='store_true', dest='echo_sql', default=False,
                      help='Echo sql code issues when state changes.')

    (options, args) = parser.parse_args()

    logfile = sys.stdout

    if options.logfile != '-':
        logfile = open(options.logfile, 'w+')

    db.setup(echo=options.echo_sql)
    db.create_all()
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db.engine)
    conn = db.engine.connect()
    session = Session(bind=conn)

    try:
        g = gevent.spawn(
            Center(session,
                   options.name,
                   options.endpoint,
                   options.controlpoint,
                   options.syncpoint,
                   options.ring,
                   logfile,
                   ).start)
        g.join()
    except Exception:
        if options.debug:
            import pdb; pdb.pm()
        else:
            raise


if __name__ == '__main__':
    main()
