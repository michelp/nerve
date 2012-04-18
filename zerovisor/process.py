from . import utils
from .states import state
from gevent import socket
from gevent import socket
from tnetstring import dumps, loads
import errno
import fcntl
import gevent
import os
import subprocess
import sys
import yaml
import zmq.green as zmq

class Popen(object):
    """
    Spawn and watch a subprocess and send interesting events to the
    zerovisor.  Acts like 'subprocess.Popen'.
    """

    identity = None
    state = state()
    
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
                 zv_hangout=False,
                 zv_restart_retries=3,
                 zv_autorestart=False,
                 zv_startsecs=1,
                 zv_exitcodes=(0,2),
                 zv_poll_interval=.1,
                 zv_ping_interval=1,
                 zv_wait_to_die=3,
                 zv_linger=0,
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

        self.hangout = zv_hangout
        self.restart_retries = zv_restart_retries
        self.restart_attempts = 0
        self.autorestart = zv_autorestart
        self.startsecs = zv_startsecs
        self.exitcodes = set(zv_exitcodes)

        self.ping_interval = zv_ping_interval
        self.poll_interval = zv_poll_interval
        self.wait_to_die = zv_wait_to_die
        self.uptime = None

        # create a connection to the zerovisor router
        self.io = self.context.socket(zmq.DEALER)
        if zv_identity is not None:
            self.io.setsockopt(zmq.IDENTITY, zv_identity)

        self.io.connect(self.endpoint)
        self.io.setsockopt(zmq.LINGER, zv_linger)

    def __getattr__(self, name):
        return getattr(self.process, name)

    def start(self):
        # start the process and then the green threads the handle the
        # various i/o and signal transits
        self.uptime = 0
        self._start_subproc()
        
        self._send('start', self.process.pid)
        self.state = state.STARTING

        # spawn workers
        self.stdiner = gevent.spawn(self._write_stdin)
        self.stdouter = gevent.spawn(self._read_stdout)
        self.stderrer = gevent.spawn(self._read_stderr)
        self.pinger = gevent.spawn(self._pinger)
        self.poller = gevent.spawn(self._poll_process)

        # wait here for the process to die naturally
        self.poller.join()

        # if poll returns, then the process is likely dead, cleanup.
        rc = self.terminate()

        #attempt a restart
        self.handle_restart(rc)

    def handle_restart(self, rc):
        if self.autorestart == False:
            return self.full_exit()
        
        if self.autorestart == True:
            return self.start()

        if 0 < self.uptime < self.startsec and self.start_attempts < self.restart_retries:
            self.start_attempts += 1
            return self.start()

        if not rc in self.exitcodes and self.autorestart == 'unexpected':
            return self.start()

        return self.full_exit()

    def terminate(self, with_exit=False):
        # terminate the possibly dead process, clean up the blood and
        # guts
        self._flush()
        # rough here sketch sucks.  If the proc hasn't died,
        # try to TERM it, then KILL it

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
        self.state = state.STOPPED
        return rc

    def alert_exit_state(self):
        """
        Assign and therefore report current exit state
        """
        if self.state == state.RUNNING:
            self.state = state.EXITED
                
        if self.state == state.STARTING:
            if self.uptime:
                self.state = state.BACKOFF
            else:
                self.state = state.FATAL
                
        if not self.state in state.exits:
            self.state = state.EXITED

        return self.state

    def full_exit(self):
        self.alert_exit_state()

        if not self.hangout:
            # stop reporting yourself live
            self.pinger.kill(block=False)

            # cleanup zeromq stuff
            self.io.close()
            self.context.term()

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

    def _send(self, op, data=None):
        payload = ['', op, dumps(data)]
        self.io.send_multipart(payload)

    def _recv(self):
        return self.io.recv_multipart()

    def _read(self, handle):
        """
        Non-blocking read
        """
        socket.wait_read(handle.fileno())
        return handle.read()

    def _write(self, handle, data):
        """
        Non-blocking write
        """
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
                self._send('rusage', [self.uptime, self.state])

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
        """
        Timekeeper and process checker.
        """
        while self.process.poll() is None:
            self.uptime += self.poll_interval
            if self.uptime > self.startsecs and self.state != state.RUNNING:
                self.start_attempts = 0
                self.state = state.RUNNING
                
            gevent.sleep(self.poll_interval)

    def _pinger(self):
        """
        While io connection to zerovisor is open, poll the process
        """
        while not self.io.closed:
            gevent.sleep(self.ping_interval)
            self._send('ping', self.process.poll())


class ZerovisorOpen(object):
    proc = Popen
    zv_defaults = dict(endpoint=None,
                       identity=None,
                       recv_in=False,
                       send_out=False,
                       send_err=False,
                       send_all=True,
                       hangout=False,
                       restart_retries=3,
                       autorestart=False,
                       startsecs=1,
                       exitcodes=(0,2),
                       poll_interval=.1,
                       ping_interval=1,
                       wait_to_die=3,
                       linger=0,
                       numproc=1,
                       name='solo')

    def __init__(self, cmd, **zv_args):
        self.numprocs = 1
        self.cmd = cmd
        self.args = zv_args
        self.args = self.update_args(self.zv_defaults.copy())
        self.commands = {}
        if self.cmd.startswith('file:'):
            commands = self.load_spec(self.cmd.replace('file:', ''))        
            args = self.update_args(self.spec.pop('defaults', {}).copy())
        else:
            self.commands[self.args.pop('name')] = dict(cmd=cmd, **self.args))
        self.running = []

    def launch_multi(self, spec, howmany):
        assert 'procname' in spec, 'numprocs requires procname to be defined'
        for procnum in range(howmany):
            spec['identity'] = spec.pop('procname', self.defprocname).format(procnum=procnum, **spec) 
            
            
    @staticmethod
    def dress_args(spec):
        spec = spec.copy()
        cmd = spec.pop('cmd').format(**spec)
        return cmd, dict(("zv_%s", val) %key for key, val in spec)

    def launch(self, **args):
        cmd, args = self.dress_args(spec) 
        p = cls.proc(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, **args)

    def initialize_procs(self):
        for name, spec in commands:
            spec = spec.copy()
            numprocs = spec.pop('numprocs', 1)
            if numprocs > 1
                self.running.extend(self.launch_multi(name, spec))
            else:
                self.running.append(self.launch(name, spec))

    @staticmethod
    def interpolate_strings(mapping):
        return dict((key, value.format(**mapping)) for key, value in mapping \
                    if isinstance(value, basestring)
    
    def update_args(self, mapping):
        """
        Nondestructive update of popen argument mapping
        """
        mapping.update(self.args)
        return mapping

    def load_spec(self, spec_file):
        with open(spec_file) as s:
            return yaml.load(spec_file)
        
    @staticmethod
    def script_args(parser):
        parser.add_argument('command',
                            help='The command or command specification to open under supervision.')
        parser.add_argument('-e', '--endpoint',
                          dest='endpoint', default='ipc://zerovisor.sock',
                          help='Specify zerovisor endpoint. default: %(default)s')

        parser.add_argument('-i', '--identity',
                          dest='identity', default=None,
                          help='Specify our identity to the zerovisor.')

        parser.add_argument('-I', '--recv-in',
                          action='store_true', dest='recv_in', default=False,
                          help='Receive stdin from zerovisor.')

        parser.add_argument('-O', '--send-out',
                          action='store_true', dest='send_out', default=False,
                          help='Send stdout to zerovisor.')

        parser.add_argument('-E', '--send-err',
                          action='store_true', dest='send_err', default=False,
                          help='Send stderr to zerovisor.')

        parser.add_argument('-A', '--send-all',
                          action='store_true', dest='send_all', default=False,
                          help='Like -IAE, receive stdin and send both stdout and stderr.')

        parser.add_argument('-s', '--restart-retries',
                          type=int, dest='restart_retries', default=3,
                          help='How many retries to allow before permanent failure. default: %(default)s')

        parser.add_argument('-p', '--ping-interval',
                          type=float, dest='ping_interval', default=3.0,
                          help='Seconds between heartbeats to zerovisor.')

        parser.add_argument('-l', '--poll-interval',
                          type=float, dest='poll_interval', default=.1,
                          help='Seconds between checking subprocess health. default: %(default)s')

        parser.add_argument('-w', '--wait-to-die',
                          type=int, dest='wait_to_die', default=3,
                          help='Seconds to wait after sending TERM to send KILL. default: %(default)s')

        parser.add_argument('-g', '--linger',
                          type=int, dest='linger', default=0,
                          help='Seconds to wait at exit for outbound messages to send, default: %(default)s')

        parser.add_argument('--autostart',
                          type=int, dest='zv_autostart', default=True,
                          help='Execute process as soon as possible default: %(default)s')
        return parser

    @classmethod
    def script(cls, args):
        zvo = cls(args.command,
                  endpoint=args.endpoint,
                  identity=args.identity,
                  recv_in=args.recv_in,
                  send_out=args.send_out,
                  send_err=args.send_err,
                  send_all=args.send_all,
                  restart_retries=args.restart_retries,
                  ping_interval=args.ping_interval,
                  poll_interval=args.poll_interval,
                  wait_to_die=args.wait_to_die,
                  linger=args.linger)

        g = gevent.spawn(p.start)
        try:
            g.join()
        except KeyboardInterrupt:
            g.kill()
            gevent.spawn(p.terminate).join()

        sys.exit(p.process.poll())


main = utils.class_to_script(ZerovisorOpen)


if __name__ == '__main__':
    main()
