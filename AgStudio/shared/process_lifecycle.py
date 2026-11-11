"""Serialize multiprocessing's process-global child bookkeeping.

Process.start calls multiprocessing.process._cleanup(), which polls *all* live
children. A per-worker lock cannot stop that poll racing a different worker's
join/waitpid and temporarily losing its exit status. All AgStudio supervisors
therefore share this lock for start, liveness, termination, reaping and close.
UI cancellation may only try to acquire it without waiting; supervisors handle
deferred cancellation on their next iteration.
"""
import threading


PROCESS_LOCK = threading.Lock()
