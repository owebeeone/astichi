# astichi-snippet: {"bind_identifier": {"first": "width", "second": "height"}}
def target(width, height):
    return (width, height)


result = target(first__astichi_arg__=1, second__astichi_arg__=2)
