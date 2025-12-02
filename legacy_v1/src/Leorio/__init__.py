import os
import sys


def add_path(path):
    if path not in sys.path:
        sys.path.insert(0, path)


# add `./src` dir to system path
src_dir = os.path.abspath(os.path.join(os.getcwd(), "../"))
add_path(src_dir)