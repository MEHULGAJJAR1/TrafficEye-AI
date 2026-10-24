"""Line-delimited JSON application logs, with no request bodies or credentials."""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        value = {'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'), 'level': record.levelname.lower(), 'logger': record.name, 'message': record.getMessage()}
        if hasattr(record, 'job_id'):
            value['job_id'] = record.job_id
        if record.exc_info:
            value['exception'] = self.formatException(record.exc_info)
        return json.dumps(value, ensure_ascii=True)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
