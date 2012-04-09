import os
import subprocess
import errno
import fcntl

import gevent
from gevent import socket
from gevent_zeromq import zmq

from tnetstring import dumps, loads


POLL_INTERVAL = .5 # how often to check if subprocess is running


class Watch(object):

    def __init__(self, endpoint, args):
        """
        Spawn a subprocess.Popen with args, watch the process and
        report to the zerovisor endpoint.
        """
        self.endpoint = endpoint
        self.context = zmq.Context()

        # create a connection to the zerovisor router
        self.io = self.context.socket(zmq.DEALER)
        self.io.connect(self.endpoint)

        # launch subprocess, with in/out/err as pipes
        self.process = proc = subprocess.Popen(args,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

        # set all pipes to be non-blocking
        fcntl.fcntl(proc.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stderr, fcntl.F_SETFL, os.O_NONBLOCK)

    def start(self):
        self._send('start', self.process.pid)
        stdin = gevent.spawn(self._write_stdin)
        stdout = gevent.spawn(self._read_stdout)
        stderr = gevent.spawn(self._read_stderr)
        poll = gevent.spawn(self._poll_process)

        poll.join() # wait here for the process to die

        stdin.kill(block=False)
        # flush outputs and join the senders so it all gets
        # sent to the zerovisor
        self._flush()
        gevent.joinall([stdout, stderr])

        # send some termination info
        rc = self.process.returncode
        if rc < 0:
            self._send('signal', rc) # killed by signal
        else:
            self._send('return',  rc) # returned code
        self.io.close()
        self.context.term()

    def _flush(self):
        self.process.stdout.flush()
        self.process.stderr.flush()

    def _send(self, op, data=None):
        self.io.send_multipart([op, dumps(data)])

    def _recv(self):
        return self.io.recv_multipart()

    def _write_stdin(self):
        stdin = self.process.stdin
        while True:
            # receive a message, and wait for the process stdin to
            # become writable.
            msg = self._recv()
            cmd = msg.pop(0)
            socket.wait_write(stdin.fileno())
            if cmd == 'in':
                while True:
                    try:
                        while msg:
                            stdin.write(msg.pop(0))
                        break
                    except IOError, e:
                        if e.args[0] != errno.EAGAIN:
                            raise

            elif cmd == 'kill':
                os.kill(self.process.pid, loads(msg[0]))

            elif cmd == 'rusage':
                pass

    def _read_stdout(self):
        stdout = self.process.stdout
        while True:
            socket.wait_read(stdout.fileno())
            data = stdout.read()
            if not data:
                return # the pipe is closed
            self._send('out', data)

    def _read_stderr(self):
        stderr = self.process.stderr
        while True:
            socket.wait_read(stderr.fileno())
            data = stderr.read()
            if not data:
                return
            self._send('err', data)

    def _poll_process(self):
        while self.process.poll() is None:
            gevent.sleep(POLL_INTERVAL)


def watch(endpoint, args):
    p = Watch(endpoint, args)
    return gevent.spawn(p.start)


def main():
    import sys
    watch(sys.argv[1], sys.argv[2:]).join()


if __name__ == '__main__':
    main()
