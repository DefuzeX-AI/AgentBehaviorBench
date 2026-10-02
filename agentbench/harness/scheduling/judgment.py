"""Bounded FIFO Judge dispatch, separate from preparation and Docker slots.

Tasks themselves are persisted by the SDK adapter before entering this queue.
Only the coordinator owns these collections; suite recovery re-enqueues the
original tickets rather than submitting another Agent attempt.
"""
from collections import deque


class JudgmentQueue:
    def __init__(self, workers=2, capacity=8):
        for name, value in (('workers', workers), ('capacity', capacity)):
            if type(value) is not int or value < 1:
                raise ValueError(f'Judge {name} must be a positive integer')
        self.workers, self.capacity = workers, capacity
        self.pending = deque()

    def can_execute(self, reserved):
        return len(self.pending) + reserved < self.capacity

    def append(self, state, job):
        self.pending.append((state, job))
