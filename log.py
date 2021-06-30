import os
import logging
from logging.handlers import TimedRotatingFileHandler
import sys


class CryptonLogger(object):

    _my_modules = ["__main__", "trade", "exchanges", "api", "api.base"]
    _log_levels = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "ERROR": logging.ERROR}
    _log_formatter = "[%(levelname)s:%(asctime)s - %(module_fields)s] %(message)s"

    def __init__(self, filename=None, level="INFO"):
        self.filename = filename
        self.level = level

    def _disable_existing_loggers(self):
        for existing_logger in logging.root.manager.loggerDict:
            if existing_logger not in self._my_modules:
                logging.getLogger(existing_logger).setLevel(logging.CRITICAL)

    def _get_console_handler(self, formatter=None):
        formatter = formatter or self._log_formatter
        formatter = logging.Formatter(formatter)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        return console_handler

    def _get_file_handler(self, formatter=None):
        formatter = formatter or self._log_formatter
        formatter = logging.Formatter(formatter)

        filename = self.filename
        log_file = os.path.join("logs", filename + ".log")
        file_handler = TimedRotatingFileHandler(log_file, when='midnight')
        file_handler.setLevel(logging.ERROR)

        file_handler.setFormatter(formatter)

        return file_handler

    def initiate(self):
        logger = logging.getLogger()

        if logger.hasHandlers():
            return

        self._disable_existing_loggers()

        self.level = self._log_levels.get(self.level.upper(), logging.INFO)
        logger.setLevel(self.level)
        logger.propagate = False

        logger.addHandler(self._get_console_handler(formatter=self._log_formatter))

        if self.filename:
            logger.addHandler(self._get_file_handler(formatter=self._log_formatter))
