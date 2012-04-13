# Intro

Zerovisor is a distributed process supervision tool written in Python
and built on top of 0mq and gevent.

Zerovisor differs from other process managers in that it is
distributed.  A zerovisor process runs on one or more machines and
"watches" other locally or remotely running processes.

Another big difference with other supervision frameworks is that there
is no "configuration file".  Based on the philosophies of 0mq, there
is no centralized point of control or configuration.

Regardless if whether a process is running locally to a zerovisor or
on some other machine, a consistent set of command-line tools is used
to manage all processes across many machines.  There is no zerovisor
"shell".  Your OS shell is the zerovisor shell!

## Installation

Zerovisor can be installed from pypi using either easy_install or pip:

    $ easy_install zerovisor
    
This will download and install the lastest version of zerovisor into
your environment.  This will install the programs 'zerovisord' and
'zvwatch':

## Getting started

Here are some examples:

Typically when using zerovisor the first task will be to create a
zerovisor process.

    $ zerovisord

This command runs a local zerovisor process and connects it to the
default endpoint 'ipc://zerovisor.sock' which creates a domain socket
of that name in the local directory where zerovisor was run.

Now a zerovisor process is running waiting for processes to monitor to
be started.  For example, consider the standard unix program 'echo':

    $ echo bob is your uncle
    bob is your uncle
    $

The echo process started, echoed its arguments to its standard output,
and then exited.  This process can be watched starting it instead with
the 'zvwatch' command:

    $ zvwatch echo bob is your uncle
    bob is your uncle
    $

Seems like nothing special happened, but the state and output of the
process was not only returned to the shell, but also sent to the
zerovisor, as can be seen by tailing the logs:

    $ tail zerovisor.log
    ['\x00k\x8bEg', 'start', 12998L]
    ['\x00k\x8bEg', 'out', 'bob is your uncle\n']
    ['\x00k\x8bEg', 'return', 0L]

The watcher process contacted the zerovisor, told it the child was
starting (and the pid), repeated the output of the program, then
indicated the process returned with code '0'.

There are 3 processes at work here: the 'zerovisor' process runs
continuously and collects data from watchers.  The 'zvwatch' process
spawns child processes and watches them for activity, sending events
and I/O data to the zerovisor, and finally there is the watched
process, blissfully doing its thing completely unaware of the
intervention of zvwatch and zerovisor.

The way zvwatch and zerovisor interact with each other by default is
over the zeromq endpoint 'ipc://zerovisor.sock'.  On unix this creates
a local unix domin socket file.  All zerovisor tools however take the
'-e' or '--endpoint' arguments to send the endpoint where the
zerovisor and the vzwatch will rendezvous.

0mq sockets can connect not only over ipc, but tcp as well.  This
allows zerovisor connections over the network:

    $ zerovisord --endpoint tcp://*:44444
    
Now the zerovisor daemon is listening on the localhost port 44444.  A
zvwatch can be launched wit the same argument:

    $ zvwatch --endpoint tcp://localhost:44444 echo bob is your uncle
    
Tail the zerovisor.log file and you will see that the same information
as before is reported to the zerovisor, but this time, over a network
connection.  The zerovisor can be running on one machine and the
watched process on another.  This is one part of the distributed
nature of zerovisor.

# Fiction below

# Controling a zerovisor

A zerovisor not only listens on a process endpoint for information
from processes, it also as a "control" endpoint that lets you interact
with the zerovisor daemon and control watched processes by sending
them input or signals and watching their response.

# Zerovisor rings

Zerovisors are not only a central athority, they also can cooperate
with other zerovisors in a "ring".  This provides a consistent
interface for controlling a whole cluster of zerovisors, which in
turn, control many processes.

# Watching zerovisors with zerovisors

'zvwatch' can be used to watch zerovisor, in turn reporting to a
"meta" zerovisor.  Typically one master zerovisor will watch a ring of
zerovisors, which in turn watch a cluster of processes.
