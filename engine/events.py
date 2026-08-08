from contextlib import contextmanager


class Event:
    def __init__(self, type_, **data):
        self.type = type_
        self.data = data


class EventBus:

    def __init__(self):
        self.subscribers = {}
        self._dispatch_depth = 0
        self._next_dispatch_root_id = 1
        self.current_dispatch_root_id = None

    def subscribe(self, event_type, fn):
        self.subscribers.setdefault(event_type, []).append(fn)

    @contextmanager
    def dispatch_scope(self):
        is_root = self._dispatch_depth <= 0
        if is_root:
            self.current_dispatch_root_id = self._next_dispatch_root_id
            self._next_dispatch_root_id += 1
        self._dispatch_depth += 1
        try:
            yield self.current_dispatch_root_id
        finally:
            self._dispatch_depth = max(0, self._dispatch_depth - 1)
            if is_root:
                self.current_dispatch_root_id = None

    def emit(self, event):
        with self.dispatch_scope() as dispatch_root_id:
            event.dispatch_root_id = dispatch_root_id
            for fn in self.subscribers.get(event.type, []):
                fn(event)
