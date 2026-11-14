import logging
import sys
from logging.config import dictConfig

def setup_logging(log_level: str = "INFO") -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "filename": "app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file"],
        },
        "loggers": {
            "uvicorn": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "fastapi": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
    }
    
    dictConfig(logging_config)
