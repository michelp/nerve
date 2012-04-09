= Intro =

Zerovisor is a distributed process supervision tool written in Python
and built on top of 0mq and gevent.

Zerovisor differs from other process managers in that it is
distributed.  A zerovisor process runs on one or more machines and
"watches" other locally or remotely running processes.  The cluster of
zerovisors can inter-communicate and treat the entire "farm" of
processes as if running on one big machine.  Whether interacting with
the entire cluster or just one zerovisor, the command line tools
behave the same.

Another big difference with other supervision frameworks is that there
is no "configuration file".  Based on the philosophies of 0mq, there
is no centralized point of control or configuration.  Zerovisor is a
collection of command-line tools that let you interconnect processes
and zerovisors by having them rendezvous at different local and remote
communication "endpoints".  All configuration options are arguments to
the zerovisor commands.

Regardless if whether a process is running locally to a zerovisor or
on some other machine, a consistent set of command-line tools is used
to manage all processes across many machines.  There is no zerovisor
"shell".  Your OS shell is the zerovisor shell!

= Getting started =

Here are some examples:

Typically when using zerovisor the first task will be to create a
zerovisor process.

  $ zerovisor

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
  $

Here the 'zvwatch' program is running the same 'echo' program, but
notice that no output was echoed.  This is because by default zvwatch
redirects all standard input and outputs to the zerovisor.  The
process started, ran, sent output, and exited, and all that
information was sent to the zerovisor, instead of to the console.
This can be seen by tailing the zerovisor log:

  $ tail zerovisor.log

There are 3 processes at work here: the 'zerovisor' process runs
continuously and collects data from watchers.  The 'zvwatch' process
spawns child processes and watches them for activity, sending events
and I/O data to the zerovisor, and finally there is the watched
process, blissfully doing its thing completely unaware of the
intervention of zwatch and zerovisor.

The way zvwatch and zerovisor interact with each other by default is
over the zeromq endpoint 'ipc://zerovisor.sock'.  On unix this creates
a local unix domin socket file.  All zerovisor tools however take the
'-e' or '--endpoint' arguments to send the endpoint where the
zerovisor and the vzwatch will rendezvous.
