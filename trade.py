import argparse

from log import Notify
from trader.looper import CryptonLooper
from trader.utils import load_settings_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-w", "--worker", type=str, help="Specify the configuration file of the worker"
    )
    parser.add_argument(
        "-s",
        "--simulate",
        default=False,
        type=bool,
        help="Simulate mode will not order",
    )
    parser.add_argument(
        "-l", "--loglevel", default="info", type=str, help="debug, info or error"
    )
    args = parser.parse_args()

    worker = args.worker
    log_level = args.loglevel

    settings = load_settings_file(worker)

    notifier = Notify(
        continuous=settings.get("log_continuously", True),
        filename=worker,
        level=log_level,
    )
    notifier.initiate()

    CryptonLooper(settings, notifier=notifier).start()
