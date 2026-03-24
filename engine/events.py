class Event:
    def __init__(self, type_, **data):
        self.type = type_
        self.data = data


class EventBus:

    def __init__(self):
        self.subscribers = {}

    def subscribe(self, event_type, fn):
        self.subscribers.setdefault(event_type, []).append(fn)

    def emit(self, event):
        for fn in self.subscribers.get(event.type, []):
            fn(event)
