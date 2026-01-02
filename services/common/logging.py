import logging
import os
import sys
import time

# Read GCP project ID (needed for trace correlation)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")

def ist_converter(*args):
    return time.gmtime(
        time.mktime(time.localtime()) + 5.5 * 3600)


def get_logger(name: str = None) -> logging.Logger:
    """
    Usage:
        logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger  # Avoid duplicate handlers

    formatter = logging.Formatter(
        fmt=(
            "[%(asctime)s] "
            "[%(levelname)s] "
            f"[{GCP_PROJECT_ID}] "
            "[%(filename)s:%(lineno)d] "
            "[%(name)s] "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    formatter.converter = ist_converter

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger