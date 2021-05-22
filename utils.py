from time import sleep

import ccxt


def handle_bad_requests(max_retries=3, sleep_between_retry=True, suppress=False):
    def decorator(func):
        def decorated_function(exchange, *args, **kwargs):
            retries = 0

            while True:
                try:
                    return func(exchange, *args, **kwargs)
                except ccxt.NetworkError as e:
                    error = e
                    retries += 1
                except ccxt.ExchangeError as e:
                    error = e
                    retries += 1
                except Exception as e:
                    error = e
                    retries += 1

                if retries > max_retries:
                    raise error

                print(
                    "Error {}. Retrying {}/{}".format(
                        type(error).__name__, retries, max_retries
                    )
                )

                if sleep_between_retry:
                    sleep(1)

        return decorated_function

    return decorator
