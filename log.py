import os
from logging import StreamHandler, getLogger, DEBUG, INFO, ERROR, Formatter
from logging.handlers import TimedRotatingFileHandler
import sys


class CryptonLogger(object):

    LOG_LEVELS = {"DEBUG": DEBUG, "INFO": INFO, "ERROR": ERROR}

    _log_formatter = "[%(levelname)s:%(asctime)s  DEFAULT] %(message)s"

    def __init__(self):
        self.level = "INFO"
        self.filename = "default_log"

    def get_console_handler(self, formatter=None):
        formatter = formatter or self._log_formatter
        formatter = Formatter(formatter)

        console_handler = StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        return console_handler

    def get_file_handler(self, formatter=None):
        formatter = formatter or self._log_formatter
        formatter = Formatter(formatter)

        filename = self.filename
        log_file = os.path.join("logs", filename + ".log")
        file_handler = TimedRotatingFileHandler(log_file, when='midnight')

        file_handler.setFormatter(formatter)

        return file_handler

    def get_root(self):
        root_logger = getLogger()

        log_level = self.LOG_LEVELS.get(self.level.upper(), DEBUG)
        root_logger.setLevel(log_level)
        root_logger.propagate = False

        return root_logger

    def get(self, name, formatter=None):
        logger = getLogger(name)

        logger.addHandler(self.get_console_handler(formatter=formatter))
        logger.addHandler(self.get_file_handler(formatter=formatter))

        return logger


logger_class = CryptonLogger()
