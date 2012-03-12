import os
import gevent
from gevent_zeromq import zmq


class Zerovisor(gevent.Greenlet):

    bind = 'tcp://*:8765'

    def __init__(self, bind=None):
        gevent.Greenlet.__init__(self)
        self.bind = bind or self.bind

    def _run(self, *args):
        self.processes = {}
        self.context = zmq.Context()
        self.router = self.context.socket(zmq.ROUTER)   
        self.router.setsockopt(zmq.IDENTITY, self.bind)
        self.router.bind(self.bind)

        while True:
            print(self.router.recv())

if __name__ == '__main__':
    from optparse import OptionParser
    from ConfigParser import ConfigParser

    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config', default='zerovisor.conf',
                      help='Specify config file', metavar='FILE')

    parser.add_option('-s', '--shell', action='store_true', dest='shell',
                      help='Launch interactive zerovisor shell')
    parser.add_option('-d', '--daemon', action='store_true', dest='shell',
                      help='Run zerovisor in the background.')

    (options, args) = parser.parse_args()
    config = options.get('config')

    configuration = ConfigParser()
    configuration.read([config,
                        'etc/zerovisor.conf',
                        os.path.expanduser('~/.zerovisor/conf'), 
                        '/etc/zerovisor.conf'])

    command, args = args[0], args[1:] if args else ('status', '*')

    config.read(['site.cfg', os.path.expanduser('~/.myapp.cfg')])
    w = Zerovisor()
    w.start()
    w.join()


