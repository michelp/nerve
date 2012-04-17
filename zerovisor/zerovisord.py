from collections import defaultdict
from contextlib import closing
from functools import wraps
from tnetstring import loads
import gevent
import sys
import zmq.green as zmq


class Zerovisor(object):

    def __init__(self, endpoint, controlpoint, pubout, logfile):
        self.endpoint = endpoint
        self.controlpoint = controlpoint
        self.logfile = logfile

        self.processes = defaultdict(dict)
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.bind(self.endpoint)

        self.control = self.context.socket(zmq.REP)
        self.control.bind(self.controlpoint)

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
        
    def _read_router(self):
        while True:
            try:
                sender, _, cmd, data = self.router.recv_multipart()
            except ValueError:
                continue
            self._publish(sender, cmd, data)
            self.logfile.write(str([sender, cmd, loads(data)])+'\n')
            self.logfile.flush()

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


@coro
def subscriber(pub, channels=None, parse=parse_pubout, timeout=500):
    """
    A generator for receiving messages from a publishing endpoint.
    
    Not really a coroutine, but it's more convenient to setup the socket
    before it will receiver messages.  The first yield creates state and
    returns `None`, the rest return msgs.
    """
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    poll = zmq.Poller()
    with closing(sock):
        if channels is None:
            channels = ['']

        for chan in channels:
            sock.setsockopt(zmq.SUBSCRIBE, chan)
            
        sock.connect(pub)
        poll.register(sock)
        yield None
        try:
            while True:
                polled_socks = dict(poll.poll(timeout))
                if polled_socks.get(sock) == zmq.POLLIN:
                    msg = sock.recv()
                    yield parse(msg)
                gevent.sleep(0.1)
        finally:
            poll.unregister(sock)

            


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

    parser.add_option('-o', '--pub-endpoint', dest='pub_endpoint', default='ipc://pub.sock',
                      help='Specify zerovisor pub endpoint.')

    parser.add_option('-c', '--controlpoint', dest='controlpoint', default='ipc://control.sock',
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
        g = gevent.spawn(Zerovisor(options.endpoint, options.controlpoint, 
                                   options.pub_endpoint, logfile).start)
        g.join()
    except Exception:
        if options.debug:
            import pdb; pdb.pm()


if __name__ == '__main__':
    main()
