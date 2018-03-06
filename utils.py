from collections import OrderedDict
import json


class Config(OrderedDict):
    def __init__(self, file, sep=':'):
        self._file = file
        self._sep = sep
        with open(file) as J:
            obj = json.load(J, object_pairs_hook=OrderedDict)
        super().__init__(obj)

    def save(self):
        with open(self._file, 'w') as J:
            json.dump(self, J, indent=2)

    def __getitem__(self, key):
        """Black magic to allow for sep nested keys"""
        path = key.split(self._sep)
        data = self
        for e in path:
            if isinstance(data, list):
                data = data[int(e)]
            else:
                data = OrderedDict.__getitem__(data, e)
        return data

    def __setitem__(self, key, item):
        path = key.split(self._sep)
        data = self
        for e in path[:-1]:
            if isinstance(data, list):
                data = data[int(e)]
            else:
                data = OrderedDict.__getitem__(data, e)
        if isinstance(data, list):
            data[int(path[-1])] = item
        else:
            OrderedDict.__setitem__(data, path[-1], item)
