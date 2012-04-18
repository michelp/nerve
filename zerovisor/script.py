import argparse
from .process import main as zvopen
from .zerovisord import Zerovisor 
from .zvctl import main as ctl
import sys


def main(argv=None):
    if argv is None: #pragma: no cover
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()    
    subparsers = parser.add_subparsers(help='commands')

    zvopen_parser = subparsers.add_parser('open', help='start a supervised process')
    zvopen_parser.set_defaults(func=zvopen)
    
    daemon_parser = subparsers.add_parser('zd', help='start a supervising daemon (or cluster)')
    Zerovisor.script_args(daemon_parser)
    daemon_parser.set_defaults(func=Zerovisor.script)
    
    ctl_parser = subparsers.add_parser('ctl', help='CLI for managing processes')
    ctl_parser.set_defaults(func=ctl)

    args = parser.parse_args(args=argv)
    return args.func(args)
