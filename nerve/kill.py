import logging
import zmq.green as zmq
from cliff.lister import Command
from cPickle import loads, dumps

class Kill(Command):

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = Command.get_parser(self, prog_name)
        parser.add_argument('uuids', nargs='+')
        return parser

    def run(self, parsed_args):
        context = zmq.Context(1)
        socket = context.socket(zmq.REQ)
        socket.connect(self.app_args.control)
        socket.send_multipart(['kill', dumps(parsed_args.uuids)])
        result = socket.recv()
        return loads(result)
