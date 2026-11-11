"""Importable spawn-process fixtures (also work with the CI's test loader)."""
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time

from AgStudio.shared.graph.core import GraphResult, calculate_graph


def inspect_runtime(snapshot):
    return GraphResult(
        ((os.getpid(), int(multiprocessing.get_start_method() == 'spawn')),
         (int(any(name.startswith('PySide') for name in sys.modules)),
          int('AgStudio.shared.lint' in sys.modules))), (), ())


def controllable_calculation(snapshot, *, started_file, ignore_terminate=False):
    if snapshot.blocks == (1,):
        if ignore_terminate and hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path(started_file).write_text(str(os.getpid()), encoding='ascii')
        # Intentionally no cancellation hook, sleep or IPC inside this loop.
        counter = 0
        while True:
            counter = (counter + 1) % 1000000
    return calculate_graph(snapshot)


def failing_calculation(snapshot):
    raise ValueError('deliberate graph failure')


def crashing_calculation(snapshot):
    os._exit(23)


def large_calculation(snapshot):
    return GraphResult(tuple((number, number) for number in range(150000)), (), ())


def malformed_calculation(snapshot):
    return None


def recoverable_calculation(snapshot):
    if snapshot.blocks == (-1,):
        raise ValueError('recoverable failure')
    if snapshot.blocks == (-2,):
        os._exit(29)
    return calculate_graph(snapshot)


def slow_graph(snapshot, *, started_path, release_path):
    """Spawn-safe calculation held in its process until the GUI test releases it."""
    with open(started_path, 'a', encoding='ascii') as started:
        started.write(f'{os.getpid()}\n')
    deadline = time.monotonic() + 12
    while not Path(release_path).exists():
        # Keep the worker CPU-bound so UI progress cannot be attributed to a
        # scoring thread voluntarily releasing the interpreter lock by sleeping.
        sum(index * index for index in range(20000))
        if time.monotonic() >= deadline:
            raise TimeoutError('test did not release the graph process')
    return calculate_graph(snapshot)

