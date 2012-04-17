from gevent import socket
from tnetstring import dumps, loads
import errno
import fcntl
import gevent
import os
import subprocess
import sys
import zmq.green as zmq


class Popen(object):
    """
    Spawn and watch a subprocess and send interesting events to the
    zerovisor.  Acts like 'subprocess.Popen'.
    """

    identity = None

    def __init__(self, args,
                 bufsize=0,
                 executable=None,
                 stdin=None,
                 stdout=None,
                 stderr=None,
                 preexec_fn=None,
                 close_fds=False,
                 shell=False,
                 cwd=None,
                 env=None,
                 universal_newlines=False,
                 startupinfo=None,
                 creationflags=0,
                 zv_endpoint=None,
                 zv_identity=None,
                 zv_recv_in=False,
                 zv_send_out=False,
                 zv_send_err=False,
                 zv_send_all=True,
                 zv_restart_retries=3,
                 zv_poll_interval=.1,
                 zv_ping_interval=1,
                 zv_wait_to_die=3,
                 zv_linger=0,
                 zv_use_ssh=None,
                 ):
        """
        Spawn a subprocess.Popen with 'args', watch the process.  See
        'zvopen --help' for description of options.
        """
        self.endpoint = zv_endpoint
        self.args = args
        self.kwargs = dict(
            bufsize=bufsize,
            executable=executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=preexec_fn,
            close_fds=close_fds,
            shell=shell,
            cwd=cwd,
            env=env,
            universal_newlines=universal_newlines,
            startupinfo=startupinfo,
            creationflags=creationflags,
            )

        self.context = zmq.Context()

        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

        self.recv_in = zv_recv_in
        self.send_out = zv_send_out
        self.send_err = zv_send_err
        if zv_send_all:
            self.recv_in = self.send_out = self.send_err = True

        self.restart_retries = zv_restart_retries
        self.ping_interval = zv_ping_interval
        self.poll_interval = zv_poll_interval
        self.wait_to_die = zv_wait_to_die

        # create a connection to the zerovisor router
        self.io = self.context.socket(zmq.DEALER)
        if zv_identity is not None:
            self.io.setsockopt(zmq.IDENTITY, zv_identity)

        if zv_use_ssh is not None:
            from zmq import ssh
            self.tunnel = ssh.tunnel_connection(self.endpoint, zv_use_ssh)
        else:
            self.io.connect(self.endpoint)

        self.io.setsockopt(zmq.LINGER, zv_linger)

    def __getattr__(self, name):
        return getattr(self.process, name)

    def start(self):
        # start the process and then the green threads the handle the
        # various i/o and signal transits
        self._start_subproc()

        self._send('start', self.process.pid)

        # spawn workers
        self.stdiner = gevent.spawn(self._write_stdin)
        self.stdouter = gevent.spawn(self._read_stdout)
        self.stderrer = gevent.spawn(self._read_stderr)
        self.pinger = gevent.spawn(self._pinger)
        self.poller = gevent.spawn(self._poll_process)

        # wait here for the process to die naturally
        self.poller.join()

        # if poll returns, then the process is likely dead, cleanup.
        self.terminate()

    def terminate(self):
        # terminate the possibly dead process, clean up the blood and
        # guts
        self._flush()
        # rough here sketch sucks.  If the proc hasn't died,
        # try to TERM it, then KILL it

        # stop reporting yourself live
        self.pinger.kill(block=False)

        # stab it repeatedly, improve the logic here
        while self.wait_to_die and self.process.poll() is None:
            self.process.terminate()
            self.wait_to_die -= 1
            gevent.sleep(1)

        # shoot it in the head
        if self.process.poll() is None:
            self.process.kill()

        # who knows what the right order of killing, flushing and
        # joining is?  This seems to work
        self.stdiner.kill(block=False)
        self._flush()
        gevent.joinall([self.stdouter, self.stderrer])

        # Finally, wait for the process to be dead.  It should be!
        self.process.wait()

        # before we go, send off the autopsy report
        rc = self.process.returncode
        if rc < 0:
            self._send('signal', rc) # killed by signal
        else:
            self._send('return',  rc) # returned code

        # cleanup zeromq stuff
        self.io.close()
        self.context.term()
        return rc

    def _start_subproc(self):
        """
        Create subprocess.Popen object and set all file descriptors
        not to block.
        """
        self.process = proc = subprocess.Popen(self.args, **self.kwargs)

        fcntl.fcntl(proc.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stderr, fcntl.F_SETFL, os.O_NONBLOCK)

    def _flush(self):
        self.process.stdin.flush()
        sys.stdout.flush()
        sys.stderr.flush()

    # send/recv helpers

    def _send(self, op, data=None):
        payload = ['', op, dumps(data)]
        self.io.send_multipart(payload)

    def _recv(self):
        return self.io.recv_multipart()

    # non-blocking helpers for read/write

    def _read(self, handle):
        socket.wait_read(handle.fileno())
        return handle.read()

    def _write(self, handle, data):
        socket.wait_write(handle.fileno())
        return handle.write(data)

    # workers below

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
            if self.send_out:
                self._send('out', data)
            if self.stdout:
                gevent.spawn(self._write, self.stdout, data)

    def _read_stderr(self):
        while True:
            data = self._read(self.process.stderr)
            if not data:
                return
            if self.send_err:
                self._send('err', data)
            if self.stderr:
                gevent.spawn(self._write, self.stderr, data)

    def _poll_process(self):
        while self.process.poll() is None:
            gevent.sleep(self.poll_interval)

    def _pinger(self):
        """
        While io connection to zerovisor is open, poll the process
        """
        while not self.io.closed:
            gevent.sleep(self.ping_interval)
            self._send('ping', self.process.poll())


def main():
    from optparse import OptionParser

    parser = OptionParser()
    parser.disable_interspersed_args()

    parser.add_option(
        '-e', '--endpoint',
        dest='endpoint', default='ipc://zerovisor.sock',
        help='Specify zerovisor endpoint.')

    parser.add_option(
        '-i', '--identity',
        dest='identity', default=None,
        help='Specify our identity to the zerovisor.')

    parser.add_option(
        '-I', '--recv-in',
        action='store_true', dest='recv_in', default=False,
        help='Receive stdin from zerovisor.')

    parser.add_option(
        '-O', '--send-out',
        action='store_true', dest='send_out', default=False,
        help='Send stdout to zerovisor.')

    parser.add_option(
        '-E', '--send-err',
        action='store_true', dest='send_err', default=False,
        help='Send stderr to zerovisor.')

    parser.add_option(
        '-A', '--send-all',
        action='store_true', dest='send_all', default=False,
        help='Like -IAE, receive stdin and send both stdout and stderr.')

    parser.add_option(
        '-s', '--restart-retries',
        type="int", dest='restart_retries', default=3,
        help='How many retries to allow before permanent failure.')

    parser.add_option(
        '-p', '--ping-interval',
        type="float", dest='ping_interval', default=3.0,
        help='Seconds between heartbeats to zerovisor.')

    parser.add_option(
        '-l', '--poll-interval',
        type="float", dest='poll_interval', default=.1,
        help='Seconds between checking subprocess health.')

    parser.add_option(
        '-w', '--wait-to-die',
        type="int", dest='wait_to_die', default=3,
        help='Seconds to wait after sending TERM to send KILL.')

    parser.add_option(
        '-g', '--linger',
        type="int", dest='linger', default=0,
        help='Seconds to wait at exit for outbound messages to send.')

    parser.add_option(
        '-S', '--use-ssh',
        dest='use_ssh', default=None,
        help='Use ssh tunnel to argument to connect to zerovisor endpoint.')

    (options, args) = parser.parse_args()

    p = Popen(args,
              stdin=sys.stdin,
              stdout=sys.stdout,
              stderr=sys.stderr,
              zv_endpoint=options.endpoint,
              zv_identity=options.identity,
              zv_recv_in=options.recv_in,
              zv_send_out=options.send_out,
              zv_send_err=options.send_err,
              zv_send_all=options.send_all,
              zv_restart_retries=options.restart_retries,
              zv_ping_interval=options.ping_interval,
              zv_poll_interval=options.poll_interval,
              zv_wait_to_die=options.wait_to_die,
              zv_linger=options.linger,
              zv_use_ssh=options.use_ssh,
              )

    g = gevent.spawn(p.start)
    try:
        g.join()
    except KeyboardInterrupt:
        g.kill()
        gevent.spawn(p.terminate).join()

    sys.exit(p.process.poll())

if __name__ == '__main__':
    main()
