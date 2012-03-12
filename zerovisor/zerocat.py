import sys
import zmq


if __name__ == '__main__':
    if '-h' in sys.argv or len(sys.argv) < 2:
        print """Get data from a zerovisor process stdout. 

Usage: %s PID
        """ % sys.argv[0]
        sys.exit(1)
    c = zmq.Context()
    stdout = c.socket(zmq.PULL)
    stdout.connect('ipc://var/ipc/%s-stdout' % sys.argv[1])
    print >> sys.stdout, stdout.recv()
