class state(object):
    """ General states taken from supervisord. Enum and messaging descriptor """
    STOPPED = 0   # The process has been stopped due to a stop
                  # request or has never been started.

    STARTING = 10 # The process is starting due to a start request.

    RUNNING = 20  # The process is running.

    BACKOFF = 30  # The process entered the STARTING state but
                  # subsequently exited too quickly to move to the
                  # RUNNING state.

    STOPPING = 40 # The process is stopping due to a stop request.

    EXITED = 100  # The process exited from the RUNNING state (expectedly or unexpectedly).

    FATAL = 200   # The process could not be started successfully.

    UNKNOWN = 1000 # unicorns

    exits = set(STOPPED, EXITED, FATAL, BACKOFF)

    def __init__(self, cmd='state'):
        self.state = self.STOPPED
        self.cmd = cmd

    def __get__(self, obj, objtype=None):
        return self.state

    def __set__(self, obj, value):
        self.state = value # validate??
        obj._send(self.cmd, value)
