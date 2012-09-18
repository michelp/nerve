import logging
import sys

from cliff.app import App
from cliff.commandmanager import CommandManager


class Nrvsh(App):

    log = logging.getLogger(__name__)

    def __init__(self):
        super(Nrvsh, self).__init__(
            description='nrv shell',
            version='0.1',
            command_manager=CommandManager('nrv.commands'),
            )

    def build_option_parser(self, description, version):
        parser = App.build_option_parser(self, description, version)
        parser.add_argument(
            '-c', '--control',
            dest='control',
            default='ipc://control.sock',
            help='Endpoint for nrv control.',
            )
        return parser

    def prepare_to_run_command(self, cmd):
        self.log.debug('prepare_to_run_command %s', cmd.__class__.__name__)

    def clean_up(self, cmd, result, err):
        self.log.debug('clean_up %s', cmd.__class__.__name__)
        if err:
            self.log.debug('got an error: %s', err)


def main(argv=sys.argv[1:]):
    myapp = Nrvsh()
    return myapp.run(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
