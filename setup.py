from setuptools import setup

with open('VERSION', 'rb') as version_file:
    version = version_file.read().strip()

setup(name='nerve',
      version=version,
      description='Distributed, zero-configuration process supervision.',
      long_description=" ".join("""
        ...
      """.split()),
      author='Michel Pelletier',
      author_email='pelletier.michel@yahoo.com',
      packages=['nerve'],
      include_package_data=True,
      install_requires="""
        pyzmq
        gevent
        tnetstring
        python-daemon
        """,
      entry_points={'console_scripts': """
        nrv-center = zerovisor.center:main
        nrv-open = zerovisor.process:main
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
