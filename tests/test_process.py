from StringIO import StringIO
import gevent
import zerovisor


def test_init():
    ep = 'ipc:///tmp/a'
    cp = 'ipc:///tmp/b'
    lf = StringIO()
    z = zerovisor.Zerovisor(ep, cp, lf)
    p = zerovisor.Popen(['echo', 'hi'], zv_endpoint=ep, zv_identity='hibob')
    zg = z.run()
    gevent.joinall([gevent.spawn(p.start)])
    gevent.sleep(0.2)
    zg.kill()
    print lf.getvalue()

    
