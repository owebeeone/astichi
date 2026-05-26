astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    astichi_hole(body)

    @astichi_insert(body, ref=Root.ClassA)
    def __astichi_contrib__Root__body__0__ClassA():
        astichi_keep(A)

        class A:
            astichi_hole(body)

            @astichi_insert(body, ref=Root.ClassA.InitA)
            def __astichi_contrib__ClassA__body__0__InitA():
                astichi_keep(self)

                def __init__(self, params__astichi_param_hole__):
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.ClassA.InitA.BodyACount)
                    def __astichi_contrib__InitA__body__0__BodyACount():
                        astichi_import(self)
                        self.astichi_ref('count')._ = astichi_pass(count, bound=True)

                    @astichi_insert(body, order=1, ref=Root.ClassA.InitA.BodyALabel)
                    def __astichi_contrib__InitA__body__1__BodyALabel():
                        astichi_import(self)
                        self.astichi_ref('label')._ = astichi_pass(label, bound=True)

                @astichi_insert(params, kind='params', ref=ParamACount)
                def __astichi_param_contrib__InitA__params__0__ParamACount(*, count):
                    pass

                @astichi_insert(params, kind='params', order=1, ref=ParamALabel)
                def __astichi_param_contrib__InitA__params__1__ParamALabel(*, label):
                    pass

    @astichi_insert(body, order=1, ref=Root.ClassB)
    def __astichi_contrib__Root__body__1__ClassB():
        astichi_keep(B)

        class B:
            astichi_hole(body)

            @astichi_insert(body, ref=Root.ClassB.InitB)
            def __astichi_contrib__ClassB__body__0__InitB():
                astichi_keep(self)

                def __init__(self, params__astichi_param_hole__):
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.ClassB.InitB.BodyBCount)
                    def __astichi_contrib__InitB__body__0__BodyBCount():
                        astichi_import(self)
                        self.astichi_ref('count')._ = astichi_pass(count, bound=True)

                    @astichi_insert(body, order=1, ref=Root.ClassB.InitB.BodyBLabel)
                    def __astichi_contrib__InitB__body__1__BodyBLabel():
                        astichi_import(self)
                        self.astichi_ref('label')._ = astichi_pass(label, bound=True)

                @astichi_insert(params, kind='params', ref=ParamBCount)
                def __astichi_param_contrib__InitB__params__0__ParamBCount(*, count):
                    pass

                @astichi_insert(params, kind='params', order=1, ref=ParamBLabel)
                def __astichi_param_contrib__InitB__params__1__ParamBLabel(*, label):
                    pass
# astichi-provenance: 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
