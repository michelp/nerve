import os
import sys
import subprocess
import errno
import fcntl

import gevent
from gevent import socket
from gevent_zeromq import zmq

from tnetstring import dumps, loads


class Watcher(object):
    """
    Watch a subprocess and send interesting events to the zerovisor.
    """

    identity = None

    def __init__(self, endpoint, args,
                 identity=None,
                 suppress_stdin=False,
                 suppress_stdout=False,
                 suppress_stderr=False,
                 restart_retries=3,
                 poll_interval=.1,
                 ping_interval=1,
                 wait_to_die=3):
        """
        Spawn a subprocess.Popen with 'args', watch the process and
        report to the zerovisor 'endpoint'.

        If 'identity' is not None, set the value of the argument as
        the upstream socket's identity, otherwise the default 0mq
        behavior of a random identity will be created.

        The 'supress_*' arguments if True will cause the stdin/out/err
        traffic to not be sent to the zerovisor.  Default is all stdio
        to the subprocess is sent.

        'restart_retries' is the number of time the watcher should try
        to restart the subprocess if it fails.  Default is 3 times.

        The 'ping_interval' is how often the process should send a
        heartbeat signal to the zerovisor.  Default is 1 second.

        'poll_interval' is how often the subprocess should be checked
        to see if it has exited.  Default is .1 seconds.
        """
        self.endpoint = endpoint
        self.args = args
        self.context = zmq.Context()

        self.suppress_stdin = suppress_stdin
        self.suppress_stdout = suppress_stdout
        self.suppress_stderr = suppress_stderr
        self.restart_retries = restart_retries
        self.ping_interval = ping_interval
        self.poll_interval = poll_interval
        self.wait_to_die = wait_to_die

        # create a connection to the zerovisor router
        self.io = self.context.socket(zmq.DEALER)
        self.io.connect(self.endpoint)
        if identity:
            self.io.setsockopt(zmq.IDENTITY, identity)
            print identity

    def start(self):
        # start the process and the green threads the handle 
        # the various i/o and signal transits
        self._start_subproc()

        self._send('start', self.process.pid)

        self.stdiner = gevent.spawn(self._write_stdin)
        self.stdouter = gevent.spawn(self._read_stdout)
        self.stderrer = gevent.spawn(self._read_stderr)
        self.pinger = gevent.spawn(self._pinger)

        self.poller = gevent.spawn(self._poll_process)

        self.poller.join() # wait here for the process to die

        self.terminate() # the process died or something, finish the
                         # job

    def terminate(self):
        # terminate the process, clean up the blood and guts
        self._flush()

        # rough here sketch sucks
        while self.wait_to_die and self.process.poll() is None:
            self.process.terminate()
            self.wait_to_die -= 1
            gevent.sleep(1)

        # knife the baby
        if self.process.poll() is None:
            self.process.kill()

        # who knows what the right order of killing, flushing and joining is?
        self.stdiner.kill(block=False)
        self._flush()
        gevent.joinall([self.stdouter, self.stderrer])
        self.process.wait()

        # return wit hte same code as the child
        rc = self.process.returncode
        if rc < 0:
            self._send('signal', rc) # killed by signal
        else:
            self._send('return',  rc) # returned code

        self.io.close()
        self.context.term()
        return rc

    def _start_subproc(self):
        # launch subprocess, with in/out/err as pipes
        self.process = proc = subprocess.Popen(self.args,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

        # set all pipes to be non-blocking
        fcntl.fcntl(proc.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stderr, fcntl.F_SETFL, os.O_NONBLOCK)

    def _flush(self):
        self.process.stdout.flush()
        self.process.stderr.flush()

    def _send(self, op, data=None):
        self.io.send_multipart([op, dumps(data)])

    def _recv(self):
        return self.io.recv_multipart()

    def _read(self, handle):
        socket.wait_read(handle.fileno())
        return handle.read()

    def _write(self, handle, data):
        socket.wait_write(handle.fileno())
        return handle.write(data)

    def _write_stdin(self):
        while True:
            msg = self._recv()
            cmd = msg.pop(0)
            if cmd == 'in':
                socket.wait_write(self.process.stdin.fileno())
                while True:
                    try:
                        while msg:
                            self.process.stdin.write(msg.pop(0))
                        break
                    except IOError, e:
                        if e.args[0] != errno.EAGAIN:
                            raise

            elif cmd == 'kill':
                os.kill(self.process.pid, loads(msg[0]))

            elif cmd == 'flush':
                self._flush()

            elif cmd == 'rusage':
                pass

    def _read_stdout(self):
        while True:
            data = self._read(self.process.stdout)
            if not data:
                return # the pipe is closed
            if not self.suppress_stdout:
                self._send('out', data)
            gevent.spawn(self._write, sys.stdout, data)

    def _read_stderr(self):
        while True:
            data = self._read(self.process.stderr)
            if not data:
                return
            if not self.suppress_stderr:
                self._send('err', data)
            gevent.spawn(self._write, sys.stderr, data)

    def _poll_process(self):
        while self.process.poll() is None:
            gevent.sleep(self.poll_interval)

    def _pinger(self):
        while True:
            gevent.sleep(self.ping_interval)
            self._send('ping', self.process.poll())


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.disable_interspersed_args()

    parser.add_option('-e', '--endpoint', 
                      dest='endpoint', default='ipc://zerovisor.sock',
                      help='Specify zerovisor endpoint.')

    parser.add_option('-i', '--identity', 
                      dest='identity', default=None,
                      help='Specify our identity to the zerovisor.')

    parser.add_option('-I', '--suppress-stdin', 
                      action='store_true', dest='suppress_stdin', default=False,
                      help='Suppress receiving stdin from zerovisor.')

    parser.add_option('-O', '--suppress-stdout', 
                      action='store_true', dest='suppress_stdout', default=False,
                      help='Suppress sending stdout to zerovisor.')

    parser.add_option('-E', '--supress-stderr', 
                      action='store_true', dest='suppress_stderr', default=False,
                      help='Suppress sending stderr to zerovisor.')

    parser.add_option('-s', '--restart-retries', 
                      type="int", dest='restart_retries', default=3, 
                      help='How many retries to allow before permanent failure.')

    parser.add_option('-p', '--ping-interval', 
                      type="float", dest='ping_interval', default=1.0,
                      help='Seconds between heartbeats to zerovisor.')

    parser.add_option('-o', '--poll-interval', 
                      type="float", dest='poll_interval', default=.1,
                      help='Seconds between checking process health.')

    parser.add_option('-w', '--wait-to-die', 
                      type="int", dest='wait_to_die', default=3,
                      help='Seconds to wait after sending TERM to send KILL.')

    (options, args) = parser.parse_args()

    w = Watcher(options.endpoint, args,
                identity=options.identity,
                suppress_stdout=options.suppress_stdout,
                suppress_stdin=options.suppress_stdin,
                suppress_stderr=options.suppress_stderr,
                restart_retries=options.restart_retries,
                ping_interval=options.ping_interval,
                poll_interval=options.poll_interval,
                wait_to_die=options.wait_to_die,
                )

    rc = gevent.spawn(w.start)
    try:
        rc.join()
    except KeyboardInterrupt:
        rc = gevent.spawn(w.terminate)
        rc.join()
    sys.exit(rc.value)

if __name__ == '__main__':
    main()
