import __init__

import os
import wmi
import redis
import logging

from Kite import config

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


class KillPyTasks(object):

    def __init__(self):
        self.redis_client = redis.StrictRedis(config.REDIS_IP,
                                              port=config.REDIS_PORT,
                                              db=config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_DB_ID)
        for _id in range(self.redis_client.llen(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR)):
            proc = self.get_python_process(param=self.redis_client.lindex(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR, _id).decode())
            for p in proc:
                self.killtask(p.Handle)
                self.print_pid_info(p)
        for _ in range(self.redis_client.llen(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR)):
            self.redis_client.lpop(config.CACHE_RECORED_OPENED_PYTHON_PROGRAM_VAR)

    @staticmethod
    def killtask(pid):
        os.system(f"taskkill /F /pid {pid} -t")

    @staticmethod
    def get_python_process(prop="python.exe", param=None):
        output = []
        w = wmi.WMI()
        for proc in w.Win32_Process(name=prop):
            if param is None:
                output.append(proc)
            else:
                if str(proc.CommandLine).find(param) >= 0:
                    output.append(proc)
        return output

    @staticmethod
    def print_pid_info(process):
        logging.info("{} | {} | {} -> killed ... ".format(process.Handle, process.Caption, process.CommandLine))


if __name__ == "__main__":
    KillPyTasks()