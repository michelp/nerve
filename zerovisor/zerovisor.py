from collections import defaultdict

import gevent

from gevent_zeromq import zmq
from tnetstring import loads


class Zerovisor(object):

    def __init__(self, endpoint, controlpoint):
        self.endpoint = endpoint
        self.controlpoint = controlpoint

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
            sender, cmd, data = self.router.recv_multipart()
            print([sender, cmd, loads(data)])


def zerovise(endpoint, controlpoint):
    z = Zerovisor(endpoint, controlpoint)
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

    (options, args) = parser.parse_args()
    zerovise(options.endpoint, options.controlpoint)


if __name__ == '__main__':
        main()
