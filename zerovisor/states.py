class state(object):
    """ General states taken from supervisord. Enum and messaging descriptor """
    STOPPED = 0    # The process has been stopped due to a stop
                   # request or has never been started.
    
    STARTING = 10  # The process is starting due to a start request.
    
    RUNNING = 20   # The process is running.
    
    BACKOFF = 30   # The process entered the STARTING state but
                   # subsequently exited too quickly to move to the
                   # RUNNING state.

    STOPPING = 40 # The process is stopping due to a stop request.

    EXITED = 100  # The process exited from the RUNNING state (expectedly or unexpectedly).

    FATAL = 200   # The process could not be started successfully.
    
    UNKNOWN = 1000  # unicorns

    exits = set((STOPPED, EXITED, FATAL, BACKOFF))
    
    def __init__(self, cmd='state'):
        """
        As well as being a data bag, `state` implements a descriptor
        protocol for use with a `Popen` object for reporting and
        tracking changes to execution state.
        """
        self.state = self.STOPPED
        self.cmd = cmd

    def __get__(self, obj, objtype=None):
        return self.state

    def __set__(self, obj, value):
        self.state = value # validate??
        self._report(obj, value)

    def _report(self, proc, value):
        value = proc.resource_info()
        proc._send(self.cmd, value)

    def __metaclass__(name, parents, attrs):
        """
        Build forward and reverse maps of the state values
        """
        cond = lambda name: not (name.startswith('_') or name == 'exits' or name.startswith('to'))
        attrs['to_int'] = dict((name, value) for name, value in attrs.items() if cond(name))
        attrs['to_str'] = dict((value, name) for name, value in attrs.items() if cond(name))
        return type(name, parents, attrs)


def check_state(state):
    def check(out):
        return out['state'] == state
    return check
