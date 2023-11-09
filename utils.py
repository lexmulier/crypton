from time import sleep
from math import floor


def sleep_now(seconds=None):
    seconds = seconds if seconds is not None else 0.1
    sleep(seconds)


def round_down(value, precision):
    precision = 10**precision
    return floor(value * precision) / precision


def rounder(value, precision=15, strip=True):
    if value is None:
        return

    rounded_value = format(round_down(value, precision), f".{precision}f")

    if strip:
        return rounded_value.rstrip("0").rstrip(".")

    return rounded_value


def exception_logger():
    def decorator(func):
        def decorated_function(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as error:
                if args[0].isclass():
                    args[0].log.exception(f"Exception for {func.__name__}: {error}")
                raise

        return decorated_function

    return decorator
