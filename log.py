import os
import logging
from logging.handlers import TimedRotatingFileHandler
import sys


def output_logs():
    def decorator(func):
        def decorated_function(*args, **kwargs):

            try:
                output = func(*args, **kwargs)
                args[0].notifier.output(to_file=args[0].ordering)
                return output
            except Exception:
                args[0].notifier.output(to_file=True)
                raise

        return decorated_function

    return decorator


class Notify(object):

    _my_modules = ["__main__", "trade", "exchanges", "api", "api.base"]
    _log_levels = {"debug": logging.DEBUG, "info": logging.INFO, "error": logging.ERROR}
    _log_formatter = "[%(levelname)s:%(asctime)s] %(message)s"

    def __init__(self, continuous=True, filename=None, level="info"):
        self.continuous = continuous
        self.filename = filename
        self.level = level

        self.messages = []

    def add(self, logger, message, log_level="info", now=False):
        if self.continuous or now:
            self.send(logger, message, log_level=log_level)
        else:
            self.messages.append((logger, message, log_level))

    def output(self, to_file=False):
        for logger, message, log_level in self.messages:
            log_level = logging.ERROR if to_file else log_level
            self.send(logger, message, log_level=log_level)

        self.messages = []

    def send(self, logger, message, log_level="info"):
        log_func = getattr(logger, log_level)
        log_func(message)

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

        self.level = self._log_levels.get(self.level.lower(), logging.INFO)
        logger.setLevel(self.level)
        logger.propagate = False

        logger.addHandler(self._get_console_handler(formatter=self._log_formatter))

        if self.filename:
            logger.addHandler(self._get_file_handler(formatter=self._log_formatter))