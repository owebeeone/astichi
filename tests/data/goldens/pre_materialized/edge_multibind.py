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
            astichi_pass(values, outer_bind=True).append(astichi_pass(first, bound=True))
            pinned = astichi_pass(first, bound=True)

        @astichi_insert(body, order=1, ref=Root.Body)
        def __astichi_contrib__Root__body__1__Body():
            astichi_pass(values, outer_bind=True).append(astichi_pass(second, bound=True))
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
