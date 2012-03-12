= Intro =

Zerovisor is a process supervision tool and framework written in
Python and built on top of 0mq and gevent.

Zerovisor differs from other process managers in that it is
distributed.  A zerovisor runs on one or more machines and supervises
locally running processes.  The cluster of zerovisors can
intercommunicate and treat the entire "farm" of processes as if
running on one big machine.

Regardless if whether a process is running locally to a zerovisor or
on some other machine, a consistent interface is used to manage all
processes.

Zerovisor consists mainly of two kinds of components, zerovisors and
processes.

= Zerovisor =

A Zerovisor can run the following commands either locally or remote:

  - Spawn or kill a process or group

  - Tail out/err logs for a process or group

  - Attach to a running process or group (redirect IO to local console)

= Usage =

The zerovisor can be run with either one off commands via the command
line or an interactive shell.

When zerovisor is started with the -i option, it launches an
interactive shell.

= Commands = 

Commands have a common format:

  command [spec] [args]

The first part is the command to be run, the 'spec' is a formatted
string specifying the target or targets of the command, args is an
optional sequence of arguments the command may require.

= Spec =

A spec is:

  [zerovisors/]pattern

If the 'zerovisors' is ommited, it defaults to '*/' which is all
zerovisors.  Otherwise it is one (or more separated by commas)
zerovisor peers.

Pattern is either a number (ore more separated by commads) specifying
a PID, or a string, specifying a process name regex to match.

Some examples:

 '*/apache' or just 'apache' will specify all apache processes.

 'server1,server2/apache' is all apache processes on server1 and server2.
 
= spawn =

'spawn' starts a new process or processes defined by spec and passes
the new processes the optional args.  The args are parsed with shlex
before being opened with subprocess.Popen.  From that point forward
the processes are monitored by the process' local zerovisor.

= kill =

Send a signal (default: TERM) the processed defined by the spec, kill
takes one optional arg specifying the signal number or name to send to
the process.

= tail =

Tail the output, error, or both of a process or group.

= attach =

Attach to a process, redirecting the current terminal to the
stdin/stdout/stderr of the processes in the spec.  Multiple outputs
are interleaved, inputs are broadcast to all processes in the spec.

Attach mode is canceled with C-c.  Currelt you cannot send C-c to a
running process.
