from .states import state 
from gevent import socket
from gevent.event import Event
from cPickle import dumps, loads
from datetime import datetime
from uuid import uuid1

import errno
import fcntl
import gevent
import os
import psutil
import subprocess
import sys
import zmq.green as zmq


class Process(object):
    """
    Spawn and watch a subprocess and send interesting events to the
    zerovisor.  Acts a lot like 'subprocess.Popen'.
    """

    process = None
    identity = None
    uuid = None
    center = None
    state = state()
    
    def __init__(self, 
                 args=None,                # popen style args
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

                 nrv_endpoint=None,     # endpoint of center
                 nrv_identity=None,     # id of 0mq socket
                 nrv_recv_in=False,     # recv stdin from cetner?
                 nrv_send_out=False,    # send stdout to center?
                 nrv_send_err=False,    # send stderr to center?
                 nrv_send_all=True,     # send/recv stdin/out/err?
                 nrv_restart_retries=3, # # of process restarts
                 nrv_autorestart=False, # restart failed process?
                 nrv_startsecs=1,       # how long to try restarting
                 nrv_exitcodes=(0,2),   # "good" exit codes, no restart
                 nrv_poll_interval=.1,  # interval to poll subprocess for life
                 nrv_ping_interval=1,   # interval to ping the center with stats
                 nrv_wait_to_die=3,     # time to wait for the subproc to die
                 nrv_linger=0,          # 0mq socket linger
                 nrv_ssh_server=None,   # ssh server to tunnel to center endpoint
                 ):
        """
        Spawn a subprocess.Popen with 'args', watch the process.  See
        'nrvopen --help' for description of options.
        """
        self.endpoint = nrv_endpoint
        self.args = args

        # pass most args to Popen, but force PIPEs for stdio
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

        self.active = Event()
        self.active.set()

        self.context = zmq.Context()

        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

        self.recv_in = nrv_recv_in
        self.send_out = nrv_send_out
        self.send_err = nrv_send_err
        if nrv_send_all:
            self.recv_in = self.send_out = self.send_err = True
            
        self.restart_retries = nrv_restart_retries
        self.restart_attempts = 0
        self.autorestart = nrv_autorestart
        self.startsecs = nrv_startsecs
        self.exitcodes = set(nrv_exitcodes)

        self.ping_interval = nrv_ping_interval
        self.poll_interval = nrv_poll_interval
        self.wait_to_die = nrv_wait_to_die
        self.uptime = None

        # create a connection to the zerovisor router
        self.io = self.context.socket(zmq.DEALER)
        if nrv_identity is not None:
            self.io.setsockopt(zmq.IDENTITY, nrv_identity)

        if nrv_ssh_server is not None:
            from zmq import ssh
            self.tunnel = ssh.tunnel_connection(self.io, self.endpoint, 
                                                nrv_ssh_server)
        else:
            self.io.connect(self.endpoint)

        self.io.setsockopt(zmq.LINGER, nrv_linger)

    def start(self):
        # start the process and then the green threads the handle the
        # various i/o and signal transits
        self.uptime = 0
        if self.args:
            self._start_subproc()
        else:
            self.state = state.WAITING

        # spawn workers
        self.stdiner = gevent.spawn(self._write_stdin)
        self.stdouter = gevent.spawn(self._read_stdout)
        self.stderrer = gevent.spawn(self._read_stderr)
        self.pinger = gevent.spawn(self._pinger)
        self.poller = gevent.spawn(self._poll_process)

        # wait here for the process to die naturally
        self.poller.join()

        # if poll returns, then the process is likely dead, cleanup.
        if self.process:
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
            self._send('signal', [self.uuid, rc]) # killed by signal
        else:
            self._send('return',  [self.uuid, rc]) # returned code
        self.state = state.STOPPED
        return rc

    def alert_exit_state(self):
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
        self.uuid = uuid1().hex
        self.process = proc = subprocess.Popen(self.args, **self.kwargs)

        fcntl.fcntl(proc.stdin, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
        fcntl.fcntl(proc.stderr, fcntl.F_SETFL, os.O_NONBLOCK)
        self.state = state.STARTING

    def _flush(self):
        if self.process:
            self.process.stdout.flush()
            self.process.stderr.flush()

    # send/recv helpers

    def _send(self, op, data=None):
        payload = ['', 'process', op, dumps(data)]
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
            assert msg.pop(0) == ''
            cmd = msg.pop(0)
            if cmd == 'kill':
                os.kill(self.process.pid, loads(msg[0]))

            elif cmd == 'center':
                self.center = msg[0]

            elif cmd == 'flush':
                self._flush()

            elif cmd == 'in':
                socket.wait_write(self.process.stdin.fileno())
                while True:
                    try:
                        while msg:
                            self.process.stdin.write(msg.pop(0))
                        break
                    except IOError, e:
                        if e.args[0] != errno.EAGAIN:
                            raise

    def resource_info(self):
        # make this pluggable??
        info = dict(uuid=self.uuid,
                    center=self.center,
                    uptime=self.uptime,
                    state_name=state.to_str[self.state],
                    state=self.state,
                    ping_time=datetime.utcnow())
        pu = self._get_psutil()
        if pu:
            info.update(pu)
        return info

    def _read_stdout(self):
        while True:
            self.active.wait()
            data = self._read(self.process.stdout)
            if not data:
                return # the pipe is closed
            if self.send_out:
                self._send('out', data)
            if self.stdout:
                gevent.spawn(self._write, self.stdout, data)

    def _read_stderr(self):
        while True:
            self.active.wait()
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
        self.active.wait()
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
            self.active.wait()
            gevent.sleep(self.ping_interval)
            self._send('ping', self.resource_info())

    def _get_psutil(self):
        if self.process.poll() is None:
            p = psutil.Process(self.process.pid)
            data = dict(
                cmdline=' '.join(p.cmdline),
                create_time=datetime.fromtimestamp(p.create_time),
                cpu_percent=p.get_cpu_percent(),
                cpu_user=p.get_cpu_times().user,
                cpu_system=p.get_cpu_times().system,
                ionice_class=p.get_ionice().ioclass,
                ionice_value=p.get_ionice().value,
                memory_rss=p.get_memory_info().rss,
                memory_vms=p.get_memory_info().vms,
                memory_percent=p.get_memory_percent(),
                num_threads=p.get_num_threads(),
                gid_real=p.gids.real,
                gid_effective=p.gids.effective,
                gid_saved=p.gids.saved,
                is_running=p.is_running(),
                name=p.name,
                nice=p.nice,
                pid=p.pid,
                ppid=p.ppid,
                status=p.status,
                terminal=p.terminal,
                uid_real=p.gids.real,
                uid_effective=p.gids.effective,
                uid_saved=p.gids.saved,
                username=p.username,
                ) 
            return data
 

def main():
    import argparse

    configs = {}
    config_file = None
    # try:
    #     if '-c' in sys.argv:
    #         config_file = sys.argv[sys.argv.index('-c') + 1]
    #     elif '--config' in sys.argv:
    #         config_file = sys.argv[sys.argv.index('--config') + 1]
    # except IndexError:
    #     print 'Must provide a config file following -c or --config option.'
    #     return

    if config_file is not None:
        import ConfigParser
        cp = ConfigParser.ConfigParser()
        cp.read(config_file)
        for o in cp.options('nrvopen'):
            configs[o] = cp.get('nrvopen', o)

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-c', '--config', 
        dest='config', default=False,
        help='Specify config file.')

    parser.add_argument(
        '-e', '--endpoint',
        dest='endpoint', 
        default=configs.get('endpoint', 'ipc://zerovisor.sock'),
        help='Specify zerovisor endpoint.')

    parser.add_argument(
        '-i', '--identity',
        dest='identity', 
        default=configs.get('identity'),
        help='Specify our identity to the zerovisor.')

    parser.add_argument(
        '-I', '--recv-in',
        action='store_true', 
        dest='recv_in', 
        default=configs.get('recv-in', False),
        help='Receive stdin from zerovisor.')

    parser.add_argument(
        '-O', '--send-out',
        action='store_true', 
        dest='send_out', 
        default=configs.get('send-out', False),
        help='Send stdout to zerovisor.')

    parser.add_argument(
        '-E', '--send-err',
        action='store_true', 
        dest='send_err', 
        default=configs.get('send-err', False),
        help='Send stderr to zerovisor.')

    parser.add_argument(
        '-A', '--send-all',
        action='store_true', 
        dest='send_all', 
        default=configs.get('send-all', False),
        help='Like -IAE, receive stdin and send both stdout and stderr.')

    parser.add_argument(
        '-s', '--restart-retries',
        type=int, 
        dest='restart_retries', 
        default=int(configs.get('restart-retries', 3)),
        help='How many retries to allow before permanent failure.')

    parser.add_argument(
        '-p', '--ping-interval',
        type=float, 
        dest='ping_interval', 
        default=float(configs.get('ping-interval', 3.0)),
        help='Seconds between heartbeats to zerovisor.')

    parser.add_argument(
        '-l', '--poll-interval',
        type=float, 
        dest='poll_interval', 
        default=float(configs.get('poll-interval', .1)),
        help='Seconds between checking subprocess health.')

    parser.add_argument(
        '-w', '--wait-to-die',
        type=int, 
        dest='wait_to_die', 
        default=int(configs.get('wait-to-die', 3)),
        help='Seconds to wait after sending TERM to send KILL.')

    parser.add_argument(
        '-g', '--linger',
        type=int, 
        dest='linger', 
        default=int(configs.get('linger', 1)),
        help='Seconds to wait at exit for outbound messages to send.')

    parser.add_argument(
        '-S', '--ssh-server',
        dest='ssh_server', 
        default=configs.get('ssh-server'),
        help='Use ssh tunnel to server to connect to zerovisor endpoint.')

    parser.add_argument(
        '-d', '--debug', 
        action='store_true', 
        dest='debug', 
        default=configs.get('debug'),
        help='Debug on unhandled error.')

    parser.add_argument('args', nargs=argparse.REMAINDER)

    args = parser.parse_args()

    p = Process(
        args.args,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        nrv_endpoint=args.endpoint,
        nrv_identity=args.identity,
        nrv_recv_in=args.recv_in,
        nrv_send_out=args.send_out,
        nrv_send_err=args.send_err,
        nrv_send_all=args.send_all,
        nrv_restart_retries=args.restart_retries,
        nrv_ping_interval=args.ping_interval,
        nrv_poll_interval=args.poll_interval,
        nrv_wait_to_die=args.wait_to_die,
        nrv_linger=args.linger,
        nrv_ssh_server=args.ssh_server,
        )

    g = gevent.spawn(p.start)
    try:
        g.join()
    except KeyboardInterrupt:
        g.kill()
        if p.process:
            gevent.spawn(p.terminate).join()
    if p.process:
        sys.exit(p.process.poll())

if __name__ == '__main__':
    main()
