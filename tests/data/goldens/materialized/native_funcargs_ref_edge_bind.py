def func_kw(**kwds):
    return kwds

class vals:
    v1 = 100
    v2 = 200
result_kw_ref = func_kw(a=vals.v1, b=vals.v2)
