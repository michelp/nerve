# Intro

Nerve is a distributed process supervision tool written in Python
and built on top of 0mq and gevent.

Nerve is distributed in the sense that the supervising program and the
process being supervised are decoupled via a 0mq communication
channel. Regardless if whether a process is running locally to a nerve
or on some other machine, a consistent set of command-line tools is
used to manage all processes across many machines.



	    +------------+             +------------+
	    |   Center   |             |   Center   |
	    |------------|             |------------|
	    |   +----+   |             |   +----+   |
	    |   |    |   |<-----------+|   |    |   |
	    |   | DB |   |             |   | DB |   |
	    |   |    |   |             |   |    |   |
	    |   +----+   |             |   +----+   |
	    +------------+             +------------+
		  +                          ^
		  |                          |
		  |                          |
		  |                          |
		  v                          +
	    +------------+             +------------+
	    |   Center   |             |   Center   |
	    |------------|             |------------|
	    |   +----+   |             |   +----+   |
	    |   |    |   |+----------->|   |    |   |
	    |   | DB |   |             |   | DB |   |
	    |   |    |   |             |   |    |   |
	    |   +----+   |             |   +----+   |
	    +------------+             +------------+
		     ^
                     |
		     |
		     |
		   +-|---------------------+
		   | |       DEALER        |
		   |-|---------------------|
		   | |         +---------+ |
	      <----|-+--stdio--|         | |
		   | |         |         | |
	      <----|-+-signals-| subproc | |
		   | |         |         | |
		   | +--stats--|         | |
		   |           +---------+ |
		   +-----------------------+

## Installation

Nerve can be installed from pypi using either easy_install or pip:

    $ easy_install nerve
    
This will download and install the lastest version of nerve into
your environment.  This will install the programs 'nerve-center' and
'nrv-open':

## Getting started

Here are some examples:

Typically when using nerve the first task will be to create a
nerve process.

    $ nrv-center

This command runs a local nerve center process and connects it to the
default endpoint 'ipc://nerve.sock' which creates a domain socket of
that name in the local directory where nerve was run.

Now a nerve process is running waiting for processes to monitor to
be started.  For example, consider the standard unix program 'echo':

    $ echo bob is your uncle
    bob is your uncle
    $

The echo process started, echoed its arguments to its standard output,
and then exited.  This process can be watched starting it instead with
the 'nrv-open' command:

    $ nrv-open echo bob is your uncle
    bob is your uncle
    $

Seems like nothing special happened, but the state and output of the
process was not only returned to the shell, but also sent to the
nerve, as can be seen by tailing the logs:

    $ tail nerve.log
    ['\x00k\x8bEg', 'start', 12998L]
    ['\x00k\x8bEg', 'out', 'bob is your uncle\n']
    ['\x00k\x8bEg', 'return', 0L]

The watcher process contacted the nerve, told it the child was
starting (and the pid), repeated the output of the program, then
indicated the process returned with code '0'.

There are 3 processes at work here: the 'nerve' process runs
continuously and collects data from watchers.  The 'nrv-open' process
spawns child processes and watches them for activity, sending events
and I/O data to the nerve, and finally there is the watched
process, blissfully doing its thing completely unaware of the
intervention of nrv-open and nerve.

The way nrv-open and nerve interact with each other by default is
over the zeromq endpoint 'ipc://nerve.sock'.  On unix this creates
a local unix domin socket file.  All nerve tools however take the
'-e' or '--endpoint' arguments to send the endpoint where the
nerve and the vzwatch will rendezvous.

0mq sockets can connect not only over ipc, but tcp as well.  This
allows nerve connections over the network:

    $ nerve-center --endpoint tcp://*:44444
    
Now the nerve daemon is listening on the localhost port 44444.  A
nrv-open can be launched wit the same argument:

    $ nrv-open --endpoint tcp://localhost:44444 echo bob is your uncle

Tail the nerve.log file and you will see that the same information
as before is reported to the nerve, but this time, over a network
connection.  The nerve can be running on one machine and the
watched process on another.  This is one part of the distributed
nature of nerve.

# Fiction below

# Controling a nerve

A nerve not only listens on a process endpoint for information
from processes, it also as a "control" endpoint that lets you interact
with the nerve daemon and control watched processes by sending
them input or signals and watching their response.

# Nerve rings

Nerves are not only a central athority, they also can cooperate
with other nerves in a "ring".  This provides a consistent
interface for controlling a whole cluster of nerves, which in
turn, control many processes.

# Watching nerves with nerves

'nrv-open' can be used to watch nerve, in turn reporting to a
"meta" nerve.  Typically one master nerve will watch a ring of
nerves, which in turn watch a cluster of processes.

# Using nerve.nrv-open.Popen

The 'nrv-open' program is a wrapper around a class that mimics the
operation of the 'subprocess.Popen' class.

Note that the nerve Popen is not a perfect clone of Popen.