from collections import defaultdict
from cPickle import dumps, loads
import gevent
import logging
import sys
import zmq.green as zmq

from . import db


logger = logging.getLogger(__name__)


class Center(object):
    """
    Process event collection.
    """
    loads = staticmethod(loads)
    dumps = staticmethod(dumps)

    def __init__(self,
                 session,
                 name,
                 endpoint,
                 logfile):

        self.session = session

        self.endpoint = endpoint
        self.logfile = logfile

        self.processes = defaultdict(dict)
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.bind(self.endpoint)

    def terminate(self):
        self.router.close()
        self.controller.kill(block=False)
        self.context.term()

    def start(self):
        router = gevent.spawn(self._read_router)
        router.join()

    def _log(self, sender, cmd, data):
        self.logfile.write(repr([sender, cmd, data])+'\n')
        self.logfile.flush()
        
    def _read_router(self):
        while True:
            try:
                sender, _, typ, cmd, raw = self.router.recv_multipart()
                data = self.loads(raw)
            except ValueError:
                continue
            self._log(sender, cmd, data)
            if typ == 'process':
                if cmd == 'ping' or cmd == 'state':
                    p = db.Process(**data)
                    self.session.merge(p)
                    self.session.commit()
                elif cmd == 'return' or cmd == 'signal':
                    query = self.session.query(db.Process)
                    query.filter(db.Process.uuid==data[0]).delete()
                    self.session.commit()
            elif typ == 'center':
                pass

    def run(self):
        return gevent.spawn(self.start)


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

    parser.add_option('-n', '--name', dest='name', default=None,
                      help="Center name.")

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
