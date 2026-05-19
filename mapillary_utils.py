import json
import logging
import pathlib
import time

CONFIG_FILE = pathlib.Path(__file__).parent / "config.json"
SEQUENCE_CACHE_FILE = pathlib.Path(__file__).parent / "sequence_cache.json"
LOG_FILE = pathlib.Path(__file__).parent / "mapillary.log"


def setup_logging():
    logger = logging.getLogger("mapillary")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    return logger


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def load_cache():
    if SEQUENCE_CACHE_FILE.exists():
        text = SEQUENCE_CACHE_FILE.read_text().strip()
        if text:
            return json.loads(text)
    return {}


def save_cache(cache):
    SEQUENCE_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def elapsed(start):
    s = int(time.monotonic() - start)
    return f"{s // 3600}:{s % 3600 // 60:02}:{s % 60:02}"