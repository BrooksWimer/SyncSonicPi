"""Central logging setup so *every* module shares the same formatter."""
import logging, sys

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)

def get_logger(name: str) -> logging.Logger:      # convenience helper
    return logging.getLogger(name)