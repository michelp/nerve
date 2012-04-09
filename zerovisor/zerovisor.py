import os

import gevent
from gevent_zeromq import zmq
from tnetstring import loads


class Zerovisor(gevent.Greenlet):

    def __init__(self, endpoint):
        gevent.Greenlet.__init__(self)
        self.endpoint = endpoint

    def _run(self, *args):
        self.processes = {}
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.bind(self.endpoint)

        while True:
            sender, cmd, data = self.router.recv_multipart()
            print([sender, cmd, loads(data)])


if __name__ == '__main__':
    from optparse import OptionParser
    from ConfigParser import ConfigParser

    parser = OptionParser()
    parser.add_option('-e', '--endpoint', dest='endpoint', default='ipc://var/zerovisor.sock',
                      help='Specify zerovisor endpoint')

    parser.add_option('-c', '--config', dest='config', default='zerovisor.conf',
                      help='Specify config file', metavar='FILE')

    parser.add_option('-s', '--shell', action='store_true', dest='shell',
                      help='Launch interactive zerovisor shell')

    parser.add_option('-d', '--daemon', action='store_true', dest='shell',
                      help='Run zerovisor in the background.')

    (options, args) = parser.parse_args()

    import pdb; pdb.set_trace()
    configuration = ConfigParser()
    configuration.read([options.config,
                        'etc/zerovisor.conf',
                        os.path.expanduser('~/.zerovisor/conf'), 
                        '/etc/zerovisor.conf'])

    w = Zerovisor(options.endpoint)
    w.start()
    w.join()


