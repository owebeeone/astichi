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
