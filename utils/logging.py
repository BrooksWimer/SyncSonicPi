import time
import sys

# Define all color constants as empty strings to disable color formatting.
HEADER = ''
BLUE = ''
GREEN = ''
YELLOW = ''
RED = ''
ENDC = ''
BOLD = ''
UNDERLINE = ''

def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}", flush=True)
    sys.stdout.flush()
