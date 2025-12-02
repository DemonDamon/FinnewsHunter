import os
import sys


def add_path(path):
    if path not in sys.path:
        sys.path.insert(0, path)


# add `./src` dir to system path
src_dir_1 = os.path.abspath(os.path.join(os.getcwd(), "../"))

# add `./src/Gon` dir to system path
src_dir_2 = os.path.dirname(__file__)

add_path(src_dir_1)
add_path(src_dir_2)