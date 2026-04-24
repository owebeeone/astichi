astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def collect(**kwds):
        return kwds

    def run(params__astichi_param_hole__):
        values = []
        astichi_hole(body)

        @astichi_insert(body, ref=Root.Body)
        def __astichi_contrib__Root__body__0__Body():
            astichi_keep(pinned)
            values.append(astichi_pass(first, bound=True))
            pinned = astichi_pass(first, bound=True)

        @astichi_insert(body, order=1, ref=Root.Body)
        def __astichi_contrib__Root__body__1__Body():
            values.append(astichi_pass(second, bound=True))
            pinned = astichi_pass(second, bound=True)
        call_result = collect(**astichi_hole(kwargs), **astichi_insert(kwargs, astichi_funcargs(a=10)), **astichi_insert(kwargs, astichi_funcargs(b=20)))
        return (first, second, values, call_result, pinned)

    @astichi_insert(params, kind='params', ref=Params)
    def __astichi_param_contrib__Root__params__0__Params(first=1):
        pass

    @astichi_insert(params, kind='params', order=1, ref=Params)
    def __astichi_param_contrib__Root__params__1__Params(second=1):
        pass
    result = run()
# astichi-provenance: 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
