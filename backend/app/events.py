"""Thread-safe latest-state broadcaster. Slow clients receive newest state, not an unbounded queue."""
import threading


class EventHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.versions = {}

    def publish(self, job_id):
        with self.lock:
            self.versions[job_id] = self.versions.get(job_id, 0) + 1

    def version(self, job_id):
        with self.lock:
            return self.versions.get(job_id, 0)
