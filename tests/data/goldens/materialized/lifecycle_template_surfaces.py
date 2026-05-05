from types import SimpleNamespace
# lifecycle template module

class ExampleState:
    __slots__ = ('_count_current', '_label_value')

    def __init__(self, *, count: int=0, label: str='x'):
        # state field initialization
        self._count_current = count
        self._label_value = label

class Example(object):
    __slots__ = ('_state',)

    def __init__(self, *, count: int=0, label: str='x'):
        self._state = ExampleState(count=count, label=label)
    # count property template

    @property
    def count(self):
        return self._state._count_current

    @count.setter
    def count(self, value):
        self._state._count_current = value
    # label property template

    @property
    def label(self):
        return self._state._label_value
result = Example(count=1, label='alpha')
result.count = 2
summary = SimpleNamespace(count=result.count, label=result.label, class_name=type(result).__name__)
