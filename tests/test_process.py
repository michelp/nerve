from StringIO import StringIO
from zerovisor.states import state 
from zerovisor.zerovisord import subscriber 
import gevent
import unittest
import zerovisor


class TestSimpleSupervision(unittest.TestCase):
    ep = 'ipc:///tmp/a'
    cp = 'ipc:///tmp/b'
    po = 'ipc:///tmp/po'


    @classmethod
    def setupAll(cls):
        cls.lf = StringIO()
        cls.z = zerovisor.Zerovisor(cls.ep, cls.cp, cls.po, cls.lf)
        cls.zg = cls.z.run()
        cls.suball = subscriber(cls.po)

    @classmethod
    def teardownAll(cls):
        cls.z.terminate()
        cls.zg.kill(block=False)
        try:
            cls.suball.throw(StopIteration)
        except :
            pass
        
    def tearDown(self):
        try:
            self.sub.throw(StopIteration)
        except :
            pass

    def makeproc(self, cmd=None,  id_='hibob'):
        p = zerovisor.Popen(cmd,
                            zv_endpoint=self.ep,
                            zv_identity=id_)
        return p

    def basic_supervision(self, cmd=['echo', 'hi']):
        #gevent.sleep(0.2)
        p = self.makeproc(cmd)
        gevent.joinall([gevent.spawn(p.start)])
        #gevent.sleep(0.5)

    def test_simple_exec(self):
        """
        Sanity test: run proc, check emitted output from zerovisord
        """
        self.basic_supervision()
        
        assert self.lf.getvalue()
        sub = self.suball

        proc, cmd, out = next(sub)
        assert (proc, cmd) == ('hibob', 'start')
        assert int(out) # something coercable to an int

        self.assert_submsg(sub, ('hibob', 'state', state.STARTING))
        self.assert_submsg(sub, ('hibob', 'out', 'hi\n'))
        self.assert_submsg(sub, ('hibob', 'return', 0))
        self.assert_submsg(sub, ('hibob', 'state', state.STOPPED))

    def assert_submsg(self, sub, (xproc, xcmd, xout)):
        candidate = proc, cmd, out = next(sub)
        expected = " ".join((xproc, xcmd, str(xout)))
        actual = " ".join(str(x) for x in candidate)
        assert proc == xproc and cmd == xcmd and out == xout, "%s != %s" %(actual, expected)

    def test_subscription_filtering(self):
        sub = subscriber(self.po, ['hibob start'])
        self.basic_supervision(['echo', 'w00t'])
        proc, cmd, _ = next(sub)
        assert cmd == 'start'













