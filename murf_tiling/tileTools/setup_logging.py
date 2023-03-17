#! python3.11

import logging
from pathlib import Path


def root_logger(log_path: str) -> logging.Logger:

    log_format = logging.Formatter(
        '%(asctime)s - '
        '%(levelname)s - '
        'line %(lineno)d - '
        '%(name)s.'
        '%(funcName)s - '
        '%(message)s'
    )
    log_folder = Path("./logs")
    if not log_folder.exists():
        log_folder.mkdir()
    log_file_handler = logging.FileHandler(
        log_path,
        mode='a'
    )
    log_file_handler.setLevel(logging.DEBUG)
    log_file_handler.setFormatter(log_format)

    log_stream_handler = logging.StreamHandler()
    log_stream_handler.setLevel(logging.CRITICAL)
    log_stream_handler.setFormatter(log_format)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_stream_handler)
    logger.addHandler(log_file_handler)

    return logger
