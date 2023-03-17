import logging


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    log_format = logging.Formatter(
        '%(asctime)s - '
        '%(levelname)s - '
        'line %(lineno)d - '
        '%(name)s.'
        '%(funcName)s - '
        '%(message)s'
    )
    fh = logging.FileHandler("log.txt", mode='a')
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.CRITICAL)
    ch.setFormatter(log_format)
    fh.setFormatter(log_format)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
