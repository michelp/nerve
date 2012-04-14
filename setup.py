from setuptools import setup

with open('VERSION', 'rb') as version_file:
    version = version_file.read().strip()

setup(name='zerovisor',
      version=version,
      description='Distributed, zero-configuration process supervision.',
      long_description=" ".join("""
        ...
      """.split()),
      author='Michel Pelletier',
      author_email='pelletier.michel@yahoo.com',
      packages=['zerovisor'],
      include_package_data=True,
      install_requires="""
        pyzmq
        gevent
        gevent_zeromq
        tnetstring
        python-daemon
        """,
      entry_points={'console_scripts': """
        zerovisord = zerovisor.zerovisord:main
        zvopen = zerovisor.zvopen:main
        zvctl = zerovisor.zvctl:main
      """},
      keywords="process supervision zeromq 0mq pyzmq gevent distributed",
      classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Hackers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries',
        'Topic :: Utilities'])
