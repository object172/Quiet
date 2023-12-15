import threading


class ItemStore(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.items = []

    def add(self, item):
        with self.lock:
            self.items.append(item)

    def get_all(self):
        with self.lock:
            items, self.items = self.items, []
        return items

    def read_all(self):
        with self.lock:
            items = self.items
            return items
