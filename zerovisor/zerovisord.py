from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from tnetstring import dumps
from tnetstring import loads
from pprint import pformat
import gevent
import logging
import sys
import zmq.green as zmq


logger = logging.getLogger(__name__)


class Zerovisor(object):
    """
    The Lord of the Prox
    """
    tns_loads = staticmethod(loads)
    tns_dumps = staticmethod(dumps)

    def __init__(self, endpoint, ctl_endpoint, pubout, logfile):
        self.endpoint = endpoint
        self.ctl_endpoint = ctl_endpoint
        self.logfile = logfile

        self.processes = defaultdict(dict)
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.bind(self.endpoint)

        self.control = self.context.socket(zmq.REP)
        self.control.bind(self.ctl_endpoint)

        self.pub = self.context.socket(zmq.PUB)
        self.pub.bind(pubout)

    def terminate(self):
        for sock in self.router, self.control, self.pub:
            sock.close()
        self.controller.kill(block=False)
        self.context.term()

    def start(self):
        router = gevent.spawn(self._read_router)
        self.controller = gevent.spawn(self._read_control)
        self.controller.join() # wait here for the controller to exit
        router.kill(block=False)

    def _read_control(self):
        while True:
            gevent.sleep(1)

    def _publish(self, proc, cmd, data):
        id_pubout = ' '.join([proc, cmd, data])
        self.pub.send(id_pubout)

    def _log(self, sender, cmd, data):
        self.logfile.write(str([sender, cmd, self.tns_loads(data)])+'\n')
        self.logfile.flush()
        
    def _read_router(self):
        while True:
            try:
                sender, _, cmd, data = self.router.recv_multipart()
            except ValueError:
                continue
            self._publish(sender, cmd, data)
            self._log(sender, cmd, data)

    def run(self):
        return gevent.spawn(self.start)
    


def coro(func):
    @wraps(func)
    def start(*args,**kwargs):
        cr = func(*args,**kwargs)
        next(cr)
        return cr
    return start


def parse_pubout(msg):
    proc, cmd, data = msg.split(' ', 2)
    return proc, cmd, loads(data)


@contextmanager
def poll_and_cleanup(sock, ctx):
    poll = zmq.Poller()
    poll.register(sock)
    try:
        yield poll 
    finally:
        # clean up
        poll.unregister(sock)
        sock.close()
        ctx.term()


@coro
def subscriber(pub, channels=None, parse=parse_pubout, timeout=500,
               retries=3, sleep=0.1, logger=logger):
    """
    A generator for receiving messages from a publishing endpoint.
    
    Not really a coroutine, but it's more convenient to setup the socket
    before it will receiver messages.  The first yield creates state and
    returns `None`, the rest return msgs.
    """
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)

    if channels is None:
        channels = ['']

    for chan in channels:
        sock.setsockopt(zmq.SUBSCRIBE, chan)
            
    sock.connect(pub)

    yield None
    retry = 0
    with poll_and_cleanup(sock, ctx) as poll:        
        while retry <= retries:
            polled_socks = dict(poll.poll(timeout))
            if polled_socks.get(sock) == zmq.POLLIN:
                msg = sock.recv()
                out = parse(msg)
                logger.debug("subscriber recv:%s", pformat(out))
                yield out
                retry = 0
            else:
                logger.debug("subscriber miss:%s", retry)
                retry += 1
            gevent.sleep(sleep)
            


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

    parser.add_option('-o', '--pub-endpoint', dest='pub_endpoint', default='ipc://pub.sock',
                      help='Specify zerovisor pub endpoint.')

    parser.add_option('-c', '--ctl-endpoint', dest='ctl_endpoint', default='ipc://control.sock',
                      help='Specify zerovisor control endpoint.')

    parser.add_option('-l', '--logfile', dest='logfile', default='zerovisor.log',
                      help='Specify the log file.')

    parser.add_option('-p', '--pidfile', dest='pidfile', default='zerovisor.pid',
                      help='Specify the pid file.')

    parser.add_option('-n', '--nodetach', action='store_false', dest='detach', default=True,
                      help='Do not detach.')

    parser.add_option('-d', '--debug', action='store_true', dest='debug', default=False,
                      help='Debug on unhandled error.')

    (options, args) = parser.parse_args()

    logfile = sys.stdout

    if options.logfile != '-':
        logfile = open(options.logfile, 'w+')
    
    try:
        import pdb; pdb.set_trace()
        g = gevent.spawn(Zerovisor(options.endpoint, options.ctl_endpoint, 
                                   options.pub_endpoint, logfile).start)
        g.join()
    except Exception:
        if options.debug:
            import pdb; pdb.pm()
        else:
            raise


if __name__ == '__main__':
    main()
