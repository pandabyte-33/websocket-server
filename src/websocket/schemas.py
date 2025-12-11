from enum import Enum


class ManagerState(Enum):
    RUNNING = 'running'
    SHUTDOWN_REQUESTED = 'shutdown_requested'
    SHUTDOWN = 'shutdown'
