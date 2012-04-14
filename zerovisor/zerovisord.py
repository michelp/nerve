import sys
import daemon

from collections import defaultdict

import gevent

from gevent_zeromq import zmq
from tnetstring import loads


class Zerovisor(object):

    def __init__(self, endpoint, controlpoint, logfile):
        self.endpoint = endpoint
        self.controlpoint = controlpoint
        self.logfile = logfile

        self.processes = defaultdict(dict)
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.bind(self.endpoint)

        self.control = self.context.socket(zmq.REP)
        self.control.bind(self.controlpoint)

    def start(self):
        router = gevent.spawn(self._read_router)
        controler = gevent.spawn(self._read_control)
        controler.join() # wait here for the controller to exit
        router.kill(block=False)

    def _read_control(self):
        while True:
            gevent.sleep(1)

    def _read_router(self):
        while True:
            try:
                sender, _, cmd, data = self.router.recv_multipart()
            except ValueError:
                continue
            self.logfile.write(str([sender, cmd, loads(data)])+'\n')
            self.logfile.flush()


def zerovise(endpoint, controlpoint, logfile):
    z = Zerovisor(endpoint, controlpoint, logfile)
    gevent.spawn(z.start).join()


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

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
        zerovise(options.endpoint, options.controlpoint, logfile)
    except Exception:
        if options.debug:
            import pdb; pdb.pm()


if __name__ == '__main__':
    main()
