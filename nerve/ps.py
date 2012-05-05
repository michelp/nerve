import logging
import zmq.green as zmq
from cliff.lister import Lister
from cPickle import loads, dumps

class Ps(Lister):

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = Lister.get_parser(self, prog_name)
        parser.add_argument(
            '-S', '--select', dest='select',
            help='Select clause to query.',
            default = ('center, uuid, pid, state_name, cmdline, cpu_percent, '
                       'memory_percent, username, uptime')
            )
        parser.add_argument(
            '-W', '--where', dest='where',
            help='Where clause to query.',
            default = None,
            )
        return parser

    def get_data(self, parsed_args):
        context = zmq.Context(1)
        socket = context.socket(zmq.REQ)
        socket.connect(self.app_args.control)
        socket.send_multipart(
            ['query', dumps((parsed_args.select, parsed_args.where))])
        result = loads(socket.recv())
        if isinstance(result, Exception):
            raise result
        return result
