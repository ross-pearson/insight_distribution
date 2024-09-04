import logging
import os
import sys
import time
from dotenv import load_dotenv


# Function to configure logging based on the environment variable
def configure_logging():
    load_dotenv()
    logging_mode = os.getenv("LOGGING_MODE", "stdout")

    if logging_mode == "stdout":
        logging.basicConfig(
            stream=sys.stdout,
            format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
            level=logging.INFO,
        )
    elif logging_mode == "file":
        log_folder = "logs"
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        logfile = os.path.join(log_folder, f'extract_disclosure_pdf_{time.strftime("%Y%m%d-%H%M%S")}.log')
        logging.basicConfig(
            filename=logfile,
            filemode="w",
            format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
            level=logging.DEBUG,
        )
    elif logging_mode == "both":
        log_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs'))
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        logfile = os.path.join(log_folder, f'extract_disclosure_pdf_{time.strftime("%Y%m%d-%H%M%S")}.log')
        logging.basicConfig(
            filename=logfile,
            filemode="w",
            format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
            level=logging.DEBUG,
        )
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        console.setFormatter(formatter)
        logging.getLogger("").addHandler(console)
    elif logging_mode == "none":
        logging.disable(logging.CRITICAL)
    else:
        raise ValueError(f"Invalid logging mode: {logging_mode}")


# Configure logging based on the environment variable
configure_logging()

# Define the logger
logger = logging.getLogger("extract_disclosure_pdf")
