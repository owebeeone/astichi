from mod1 import a, b, c
from mod2 import a as a__astichi_scoped_1, b as b__astichi_scoped_2, d

def f1():
    return (a, b, c) + (a__astichi_scoped_1, b__astichi_scoped_2) + (a__astichi_scoped_1, d)
