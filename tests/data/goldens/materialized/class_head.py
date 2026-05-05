class SingleBase(BaseRoot):
    pass

class MultiBase(BaseA, BaseB):
    pass

class WithMeta(BaseRoot__astichi_scoped_1, metaclass=Meta):
    pass

class WithKeywords(BaseRoot__astichi_scoped_1, metaclass=Meta__astichi_scoped_2, flag=True):
    pass
