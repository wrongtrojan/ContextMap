import logging
from enum import Enum
from threading import Lock

logger = logging.getLogger("SystemStateManager")

class SystemStatus(Enum):
    IDLE = "IDLE"
    INGESTING = "INGESTING"  # Track A: Processing assets
    QUERYING = "QUERYING"    # Track B: RAG / Brain Reasoning
    ERROR = "ERROR"

class SystemStateManager:
    """
    Manages the global state of the AcademicAgent-Suite.
    Ensures mutual exclusion between asset ingestion and user querying
    to protect GPU VRAM and data integrity.
    """
    _instance = None
    _state_lock = Lock()

    def __new__(cls):
        with cls._state_lock:
            if cls._instance is None:
                cls._instance = super(SystemStateManager, cls).__new__(cls)
                cls._instance._current_status = SystemStatus.IDLE
                cls._instance._task_id = None
                cls._instance._task_progress = {}  # {component_name: percentage}
                cls._instance._active_assets = []  # List of filenames being processed
                cls._instance._status_message = "System Ready"
            return cls._instance

    def acquire_ingestion_lock(self, task_id: str) -> bool:
        """Attempt to lock the system for asset processing."""
        with self._state_lock:
            if self._current_status == SystemStatus.IDLE:
                self._current_status = SystemStatus.INGESTING
                self._task_id = task_id
                logger.info(f"Lock ACQUIRED for Ingestion Task: [{task_id}]")
                return True
            else:
                logger.warning(f"Lock DENIED for Task [{task_id}]. System is {self._current_status.value}")
                return False

    def acquire_query_lock(self) -> bool:
        with self._state_lock:
            if self._current_status == SystemStatus.IDLE:
                self._current_status = SystemStatus.QUERYING
                logger.info("Lock ACQUIRED for Querying.")
                return True
            else:
                logger.warning(f"Lock DENIED for Query. System is {self._current_status.value}")
                return False
    
    def release_lock(self):
        with self._state_lock:
            old_status = self._current_status
            self._current_status = SystemStatus.IDLE
            self._task_id = None
            self._task_progress = {}
            self._active_assets = []
            self._status_message = "System Ready"
            logger.info(f"System state transitioned from {old_status.value} to IDLE.")

    @property
    def get_status(self) -> SystemStatus:
        return self._current_status

    def is_query_allowed(self) -> bool:
        """Check if the Brain is available for user questions."""
        # Ensure status is strictly IDLE to allow querying
        with self._state_lock:
            return self._current_status == SystemStatus.IDLE
        
    def update_progress(self, component: str, percentage: float, message: str = None):
        """Update the progress of a specific component during ingestion."""
        with self._state_lock:
            self._task_progress[component] = percentage
            if message:
                self._status_message = message
            logger.info(f"Progress Update - [{component}]: {percentage}% | {message}")

    def set_active_assets(self, assets: list):
        """Set the list of assets currently being processed."""
        with self._state_lock:
            self._active_assets = assets

    def get_full_state(self) -> dict:
        """Export a snapshot of the current state for Web API consumption."""
        with self._state_lock:
            return {
                "status": self._current_status.value,
                "task_id": self._task_id,
                "progress": self._task_progress,
                "active_assets": self._active_assets,
                "message": self._status_message
            }

    def reset_progress(self):
        """Clear progress data after task completion."""
        with self._state_lock:
            self._task_progress = {}
            self._active_assets = []
            self._status_message = "IDLE"    