from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    )

from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()
engine = None


def setup(path='sqlite:///:memory:', echo=False):
    global engine
    if engine is None:
        engine = create_engine(path, echo=echo)


def create_all():
    Base.metadata.create_all(engine)


class Center(Base):
    __tablename__ = 'center'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    endpoint = Column(String)
    controlpoint = Column(String)
    pubpoint = Column(String)
    next_id = Column(Integer, ForeignKey("center.id"))
    next = relationship("Center", uselist=False, 
                        backref=backref('prev', remote_side=[id]))


class Process(Base):
    __tablename__ = 'process'
    center_id = Column(Integer, ForeignKey("center.id"))
    center = relationship("Center", uselist=False,
                          backref=backref('processes'))

    uuid = Column(String, primary_key=True)
    name = Column(String)
    pid = Column(Integer)
    identity = Column(String)
    create_time = Column(DateTime)

    state = Column(Integer, nullable=False)
    state_name = Column(String, nullable=False)

    return_code = Column(Integer)
    signal = Column(Integer)
    cmdline = Column(String)
    cpu_percent = Column(Integer)
    cpu_user = Column(Integer)
    cpu_system = Column(Integer)
    ionice_class = Column(Integer)
    ionice_value = Column(Integer)
    memory_rss = Column(Integer)
    memory_vms = Column(Integer)
    memory_percent = Column(Integer)
    num_threads = Column(Integer)
    gid_real = Column(Integer)
    gid_effective = Column(Integer)
    gid_saved = Column(Integer)
    is_running =  Column(Boolean)
    nice = Column(Integer)
    ppid = Column(Integer)
    status = Column(Integer)
    terminal = Column(String)
    uid_real = Column(Integer)
    uid_effective = Column(Integer)
    uid_saved = Column(Integer)
    username = Column(String)
    uptime = Column(Float)
    ping_time = Column(DateTime)
