from __future__ import annotations

import logging
import logging.config


def configure_logging(level: int = logging.INFO) -> None:
    """Configure app and uvicorn loggers to always write to console."""
    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S',
                },
                'access': {
                    # Uvicorn emits access data via args into %(message)s in current versions.
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout',
                },
                'access_console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'access',
                    'stream': 'ext://sys.stdout',
                },
            },
            'loggers': {
                'app': {
                    'handlers': ['console'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn': {
                    'handlers': ['console'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn.error': {
                    'handlers': ['console'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn.access': {
                    'handlers': ['access_console'],
                    'level': level,
                    'propagate': False,
                },
            },
            'root': {
                'handlers': ['console'],
                'level': level,
            },
        }
    )
