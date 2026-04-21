def func_combined(head, *args, **kwds):
    return (head, args, kwds)

def func_plain(*args, **kwds):
    return (args, kwds)

def func_star(*args):
    return args

def func_kw(**kwds):
    return kwds

def func_one(head, *args, **kwds):
    return (head, args, kwds)
source_plain_scoped = 100
seed_star_scoped = 200
source_kw_scoped = 300
head_supply = 1
seed_star = 2
result_combined = func_combined('head_slot', 2, fixed=1, **{'seed': {'seed': 101}}, name='x', flag=True)
result_plain = func_plain(20, fixed=2)
result_star = func_star(7)
result_kw = func_kw(fixed=4, msg='solo')
result_plain_scoped = func_plain(((out := source_plain_scoped), (__astichi_assign__inst__PlainScoped__name__out := out))[0], fixed=2)
result_star_scoped = func_star(((out__astichi_scoped_1 := seed_star_scoped), (__astichi_assign__inst__StarScoped__name__out := out__astichi_scoped_1))[0])
result_kw_scoped = func_kw(fixed=4, msg=((out__astichi_scoped_2 := source_kw_scoped), (__astichi_assign__inst__KwScoped__name__out := out__astichi_scoped_2))[0])
result_multi_scope = func_one(((out__astichi_scoped_3 := head_supply), (__astichi_assign__inst__HeadMulti__name__out := out__astichi_scoped_3))[0], (out__astichi_scoped_4 := seed_star), fixed=1, **{'seed': {'seed': 101}}, name='x', flag=True)
out_multi_scope = __astichi_assign__inst__HeadMulti__name__out
out_kw_scoped = __astichi_assign__inst__KwScoped__name__out
out_star_scoped = __astichi_assign__inst__StarScoped__name__out
out_plain_scoped = __astichi_assign__inst__PlainScoped__name__out
