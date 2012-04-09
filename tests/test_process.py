import multiprocessing
import gevent
import zerovisor


def test_init():
    ep = 'ipc:///tmp/a'
    z = zerovisor.Zerovisor(ep)
    z.start()
    p = zerovisor.Process(ep, ['echo', 'hi'])
    p.start()
    gevent.joinall([z, p])
    
    
