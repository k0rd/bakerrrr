class ECS:

    def __init__(self):
        self.next_id = 1
        self.components = {}

    def create(self):
        eid = self.next_id
        self.next_id += 1
        return eid

    def add(self, eid, component):
        t = type(component)
        self.components.setdefault(t, {})[eid] = component

    def get(self, component_type):
        return self.components.get(component_type, {})
