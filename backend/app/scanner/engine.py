from typing import Dict, Any

class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ScanEngine:
    def __init__(self):
        self.modules = {}
    def register_module(self, module):
        name = getattr(module, 'name', str(type(module).__name__))
        self.modules[name] = module

scan_engine = ScanEngine()
