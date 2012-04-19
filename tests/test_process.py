"""
Functional tests for process running
"""
from StringIO import StringIO
from contextlib import contextmanager
from pprint import pformat
from zerovisor.states import state 
from zerovisor.zerovisord import subscriber
import gevent
import logging
import nose.tools as nt
import operator as op
import unittest
import zerovisor

logger = logging.getLogger(__name__)


def setup():
    """
    Start single zerovisor to handle communication for this roundtrip
    functional testing
    """
    setup.ep = 'ipc:///tmp/a'
    setup.cp = 'ipc:///tmp/b'
    setup.po = 'ipc:///tmp/po'    
    setup.logfile = StringIO()
    logger.info("starting zerovisord")
    setup.zerovisor = zerovisor.Zerovisor(setup.ep,
                                          setup.cp,
                                          setup.po,
                                          setup.logfile)
    setup.zvg = setup.zerovisor.run()

def teardown():
    logger.info("killing zerovisord")
    setup.zerovisor.terminate()
    setup.zvg.kill(block=False)


class SimpleBase(unittest.TestCase):

    @classmethod
    def setupAll(cls):
        """
        Setup a subber for all the tests and prime with a message from 
        """
        logger.info("starting subscriber")
        cls.suball = subscriber(setup.po)
        gevent.sleep(0.2)


    @classmethod
    def teardownAll(cls):
        """kill the subscriber"""
        try:
            logger.info("Killing subscriber")
            setup.suball.throw(StopIteration)
        except :
            pass        

    def setUp(self):
        self.submsg_tests = []
        setup.zerovisor.logfile = StringIO()
        self.basic_supervision()

    def makeproc(self, cmd=None,  id_='hibob'):
        p = zerovisor.Popen(cmd,
                            zv_endpoint=setup.ep,
                            zv_identity=id_)
        return p

    def basic_supervision(self, cmd=['echo', 'hi']):
        p = self.makeproc(cmd)
        gevent.joinall([gevent.spawn(p.start)])

    def check_msg(self, sub, (xproc, xcmd, xout), out_test=op.eq):
        candidate = proc, cmd, out = next(sub)
        expected = " ".join((xproc, xcmd, pformat(xout)))
        actual = " ".join(str(x) for x in candidate)
        result = proc == xproc and cmd == xcmd and out_test(out, xout), "%s != %s" %(actual.strip(), expected)
        self.submsg_tests.append((result, actual, expected))
        return result


@nt.with_setup(SimpleBase.setupAll, SimpleBase.teardownAll)
def test_pubsub():
    setup.zerovisor._publish('howdy', 'subscriber', setup.zerovisor.tns_dumps(True))
    check = next(SimpleBase.suball)[2]
    check and logger.info("subscriber talking to zerovisor: yes")
    not check and logger.info("subscriber talking to zerovisor: no")
    assert check


def format_condition((number, result, actual, expected)):
    if result is False:
        result = "** False **"
    out = "%d. %s %s %s" %(number, result, actual, expected)
    return out.rjust(4)
    

@contextmanager
def assert_conditions(cons, format=format_condition):
    """
    On exit, checks a list of conditions and raises an assertion error
    if any of them are False.  A formated representation of the list
    is added to the AssertionError.
    
    `cons`: list of 3 element tuples where the first member of the
    collection is coercable to a boolean::

    >>> [False, actual_value, expected_value]
    """
    try:
        yield
    finally:
        if False in set(bool(x[0]) for x in cons):
            out = "\n".join(format(num, con) for num, con in enumerate(cons))
            raise AssertionError("Failing condition(s):\n %s" %out)





class TestSimpleSupervision(SimpleBase):

    def test_write_log(self):
        assert setup.zerovisor.logfile.getvalue()

    def test_simple_exec(self):
        """
        Sanity test: run proc, check emitted output from zerovisord
        """
        sub = self.suball                
        with assert_conditions(self.submsg_tests):
            self.check_msg(sub, ('hibob', 'state', state.STARTING))
            self.check_msg(sub, ('hibob', 'out', 'hi\n'))
            self.check_msg(sub, ('hibob', 'return', 0))
            self.check_msg(sub, ('hibob', 'state', state.STOPPED))
















