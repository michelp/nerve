import sys
import os
import subprocess
import errno
import fcntl

import gevent
from gevent import socket
from gevent_zeromq import zmq


class Process(gevent.Greenlet):

    def __init__(self, args, zerovisor_ep):
        self.zerovisor_ep = zerovisor_ep
        gevent.Greenlet.__init__(self)
        self.args = args
        self.context = zmq.Context()

    def _init(self):

        # launch subprocess, with in/out/err as pipes
        self.process = subprocess.Popen(self.args,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

        # set all pipes to be non-blocking
        fcntl.fcntl(self.process.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(self.process.stderr, fcntl.F_SETFL, os.O_NONBLOCK)

        self.zerovisor = self.context.socket(zmq.ROUTER)
        self.stdout.connect(self.zerovisor_io)

    def _run(self, *args):
        self._init()
        try:
            gevent.joinall([gevent.spawn(j) for j in 
                            (self._write_stdin, 
                             self._read_stdout,
                             self._read_stderr,
                             self._poll_process,
                             )])
        finally:
            self.context.term()

    def _write_stdin(self):
        while True:
            msg = self.stdin.recv()
            socket.wait_write(self.process.stdin.fileno())
            while True:
                try:
                    self.process.stdin.write(msg)
                    break
                except IOError, e:
                    if e.args[0] != errno.EAGAIN:
                        raise

    def _read_stdout(self):
        while True:
            socket.wait_read(self.process.stdout.fileno())
            while True:
                try:
                    data = self.process.stdout.read()
                    break
                except IOError, e:
                    if e.args[0] != errno.EAGAIN:
                        raise

            self.stdout.send(data)

    def _read_stderr(self):
        while True:
            socket.wait_read(self.process.stderr.fileno())
            while True:
                try:
                    data = self.process.stderr.read()
                    break
                except IOError, e:
                    if e.args[0] != errno.EAGAIN:
                        raise

            self.stdout.send(data)

    def _poll_process(self):
        while True:
            if self.process.poll() is not None:
                rc = self.process.returncode
                if rc < 1:
                    self.control.send('signal:%s' % rc)
                else:
                    self.control.send('control:%s' % rc)
                self.context.term()
                sys.exit(1)
            gevent.sleep(1)


if __name__ == '__main__':
    w = Process(sys.argv[1:])
    try:
        w.start()
        w.join()
    finally:
        pid = w.process.pid
        os.unlink(w.bind % (pid, 'stdout'))
        os.unlink(w.bind % (pid, 'stderr'))
        os.unlink(w.bind % (pid, 'stdin'))
