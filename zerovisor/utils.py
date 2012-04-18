import sys

def class_to_script(klass):
    def main(argv=None):
        if argv is None: #pragma: no cover
            argv = sys.argv[1:]

        import argparse
        parser = klass.script_args(argparse.ArgumentParser())
        args = parser.parse_args(args=argv)
        klass.script(args)
    return main
