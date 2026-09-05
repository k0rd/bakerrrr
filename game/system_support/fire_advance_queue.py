"""Ordered fire work, grouped by due time, chunk and floor.

Overflow and unloaded work move as buckets, without visiting their cells. The
coordinate heaps have indexed removal, so suppression/rescheduling cannot leave
an unbounded pile of stale entries to clean up on a later simulation tick.
"""

from __future__ import annotations

import heapq


class _IndexedHeap:
    def __init__(self):
        self.rows = []
        self.positions = {}

    def __len__(self):
        return len(self.rows)

    def first(self):
        return self.rows[0][1]

    def set(self, key, priority):
        self.remove(key)
        index = len(self.rows)
        self.rows.append((priority, key))
        self.positions[key] = index
        self._up(index)

    def _swap(self, a, b):
        self.rows[a], self.rows[b] = self.rows[b], self.rows[a]
        self.positions[self.rows[a][1]] = a
        self.positions[self.rows[b][1]] = b

    def _up(self, index):
        while index:
            parent = (index - 1) // 2
            if self.rows[parent] <= self.rows[index]:
                break
            self._swap(parent, index)
            index = parent
        return index

    def remove(self, key):
        index = self.positions.pop(key, None)
        if index is None:
            return
        last = self.rows.pop()
        if index == len(self.rows):
            return
        self.rows[index] = last
        self.positions[last[1]] = index
        index = self._up(index)
        while 2 * index + 1 < len(self.rows):
            child = 2 * index + 1
            if child + 1 < len(self.rows) and self.rows[child + 1] < self.rows[child]:
                child += 1
            if self.rows[index] <= self.rows[child]:
                break
            self._swap(index, child)
            index = child

    def pop(self):
        key = self.first()
        self.remove(key)
        return key


class _Coordinates:
    """Use cheap set operations for small buckets; order large ones once."""

    def __init__(self):
        self.members = set()
        self.ordered = None

    def __len__(self):
        return len(self.members)

    def first(self):
        return self.ordered.first() if self.ordered is not None else min(self.members)

    def add(self, coord):
        self.members.add(coord)
        if self.ordered is not None:
            self.ordered.set(coord, coord)
        elif len(self.members) > 96:
            self.ordered = _IndexedHeap()
            self.ordered.rows = [(key, key) for key in self.members]
            heapq.heapify(self.ordered.rows)
            self.ordered.positions = {row[1]: i for i, row in enumerate(self.ordered.rows)}

    def remove(self, coord):
        self.members.remove(coord)
        if self.ordered is not None:
            self.ordered.remove(coord)


class FireAdvanceQueue:
    def __init__(self):
        self.by_coord = {}
        self.buckets = {}
        self.insertion_buckets = {}
        self.due = _IndexedHeap()
        self.serial = 0

    def __len__(self):
        return len(self.by_coord)

    def tick_for(self, coord):
        bucket_id = self.by_coord.get(coord)
        return self.buckets[bucket_id][0] if bucket_id is not None else None

    def schedule(self, coord, tick, chunk):
        bucket_id = self.by_coord.get(coord)
        if bucket_id is not None and self.buckets[bucket_id][:3] == (tick, chunk, coord[2]):
            return
        self.remove(coord)
        group = (tick, chunk, coord[2])
        bucket_id = self.insertion_buckets.get(group)
        if bucket_id is None:
            bucket_id = self.serial
            self.serial += 1
            self.buckets[bucket_id] = (*group, _Coordinates())
            self.insertion_buckets[group] = bucket_id
            self.due.set(bucket_id, tick)
        self.buckets[bucket_id][3].add(coord)
        self.by_coord[coord] = bucket_id

    def _forget_insertion_bucket(self, bucket_id, bucket):
        if self.insertion_buckets.get(bucket[:3]) == bucket_id:
            self.insertion_buckets.pop(bucket[:3])

    def remove(self, coord):
        bucket_id = self.by_coord.pop(coord, None)
        if bucket_id is None:
            return False
        bucket = self.buckets[bucket_id]
        bucket[3].remove(coord)
        if not bucket[3]:
            self._forget_insertion_bucket(bucket_id, bucket)
            self.buckets.pop(bucket_id)
            self.due.remove(bucket_id)
        return True

    def _defer_bucket(self, bucket_id, tick):
        bucket = self.buckets.get(bucket_id)
        if bucket is None:
            return
        self._forget_insertion_bucket(bucket_id, bucket)
        bucket = (tick, *bucket[1:])
        self.buckets[bucket_id] = bucket
        self.insertion_buckets.setdefault(bucket[:3], bucket_id)
        self.due.set(bucket_id, tick)

    def take_batch(self, tick, *, player_z, chunk_loaded, foreground_cap, background_cap, interval):
        ready = [[], []]
        counts = [0, 0]
        pending = []
        unloaded = []
        while self.due and self.buckets[self.due.first()][0] <= tick:
            bucket_id = self.due.pop()
            _, chunk, z, coords = self.buckets[bucket_id]
            if not chunk_loaded(chunk):
                unloaded.append(bucket_id)
                continue
            lane = 0 if player_z is None or z == player_z else 1
            counts[lane] += len(coords)
            ready[lane].append((coords.first(), bucket_id))
            pending.append(bucket_id)
        if not pending and not unloaded:
            return (), (), counts, False
        selected = [[], []]
        for lane, cap in enumerate((foreground_cap, background_cap)):
            if counts[lane] <= cap:
                # A whole eligible lane fits. Discard its heaps together;
                # sorting here is bounded by the advancement cap.
                for _, bucket_id in ready[lane]:
                    bucket = self.buckets.pop(bucket_id)
                    self._forget_insertion_bucket(bucket_id, bucket)
                    selected[lane].extend(bucket[3].members)
                selected[lane].sort()
                for coord in selected[lane]:
                    self.by_coord.pop(coord)
                continue
            heapq.heapify(ready[lane])
            while ready[lane] and len(selected[lane]) < cap:
                coord, bucket_id = heapq.heappop(ready[lane])
                selected[lane].append(coord)
                self.remove(coord)
                bucket = self.buckets.get(bucket_id)
                if bucket is not None:
                    heapq.heappush(ready[lane], (bucket[3].first(), bucket_id))
        for bucket_id in pending:
            self._defer_bucket(bucket_id, tick + 1)
        for bucket_id in unloaded:
            self._defer_bucket(bucket_id, tick + interval)
        return tuple(selected[0]), tuple(selected[1]), counts, True
