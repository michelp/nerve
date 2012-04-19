class state(object):
    """ General states taken from supervisord. Enum and messaging descriptor """
    STOPPED = 0,   # The process has been stopped due to a stop
                   # request or has never been started.
    
    STARTING = 10 # The process is starting due to a start request.
    
    RUNNING = 20  # The process is running.
    
    BACKOFF = 30  # The process entered the STARTING state but
                   # subsequently exited too quickly to move to the
                   # RUNNING state.

    STOPPING = 40 # The process is stopping due to a stop request.

    EXITED = 100  # The process exited from the RUNNING state (expectedly or unexpectedly).

    FATAL = 200   # The process could not be started successfully.
    
    UNKNOWN = 1000  # unicorns
    
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
        self._report(value)

    def _report(self, proc, cmd, value):
        value = proc.resource_info()
        proc._send(self.cmd, value)

    def __new__(cls):
        """
        Build forward and reverse maps of the state values
        """
        cls.to_int = {}
        cls.to_str = {}
        for attr in dir(cls):
            value = getattr(cls, attr)
            if not (attr.startswith('_') or isinstance(value, dict)):
                cls.to_str[value] = attr
                cls.to_int[attr] = value
        cls.exits = set((cls.STOPPED, cls.EXITED, cls.FATAL, cls.BACKOFF))
