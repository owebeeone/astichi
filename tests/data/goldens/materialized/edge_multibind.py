def collect(**kwds):
    return kwds

def run(first=1, second=1):
    values = []
    values.append(first)
    pinned = first
    values.append(second)
    pinned__astichi_scoped_1 = second
    call_result = collect(a=10, b=20)
    return (first, second, values, call_result, pinned)
result = run()
