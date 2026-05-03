from mod1 import a, b, c
from mod2 import a as a__astichi_scoped_1, b as b__astichi_scoped_2, d

def f1():
    return (a, b, c)

def f2():
    return (a__astichi_scoped_1, b__astichi_scoped_2)

def f3():
    return (a__astichi_scoped_1, d)
