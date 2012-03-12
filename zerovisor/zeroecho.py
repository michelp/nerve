import sys
import zmq


if __name__ == '__main__':
    if '-h' in sys.argv or len(sys.argv) < 3:
        print """Echo data to a zerovisor process stdin. 

Usage: %s PID data
        """ % sys.argv[0]
        sys.exit(1)
    c = zmq.Context()
    stdin = c.socket(zmq.PUSH)
    stdin.connect('ipc://var/ipc/%s-stdin' % sys.argv[1])
    stdin.send(sys.argv[2])
