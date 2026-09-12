"""Serialize plugin changes with the admission of work that needs supervision.

Hold this lock through the admission check and durable reservation, then release
it before provisioning or running the job. Disable holds it through the safety
check and configuration write, so neither side can slip between the other's
check and commit. The desktop server uses threads in a single process.
"""
import threading

state_change_lock = threading.RLock()
