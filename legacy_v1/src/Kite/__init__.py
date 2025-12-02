import os
import sys


def add_path(path):
    if path not in sys.path:
        sys.path.insert(0, path)


this_dir = os.path.dirname(__file__)

# add `./src/Kite` dir to system path
add_path(this_dir)