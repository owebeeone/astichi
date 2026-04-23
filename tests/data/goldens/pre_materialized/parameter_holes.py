astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def run(params__astichi_param_hole__):
        astichi_hole(body)

        @astichi_insert(body, ref=Root.BodyUsesParam)
        def __astichi_contrib__Root__body__0__BodyUsesParam():
            value = astichi_pass(session, outer_bind=True)

        @astichi_insert(body, order=1, ref=Root.BodyLocalCollision)
        def __astichi_contrib__Root__body__1__BodyLocalCollision():
            session = 'local'
            local_session = session
        return session

    @astichi_insert(params, kind='params', ref=Params)
    def __astichi_param_contrib__Root__params__0__Params(session, limit: astichi_insert(limit_type, int)=5, *items, debug=False, **options):
        pass

    async def async_run(async_params__astichi_param_hole__):
        return token

    @astichi_insert(async_params, kind='params', ref=AsyncParams)
    def __astichi_param_contrib__Root__async_params__0__AsyncParams(token):
        pass

    def foo(p1__astichi_param_hole__, user_param, p2__astichi_param_hole__):
        user_code(user_param)
        return (before, user_param, after)

    @astichi_insert(p1, kind='params', ref=P1)
    def __astichi_param_contrib__Root__p1__0__P1(before):
        pass

    @astichi_insert(p2, kind='params', ref=P2)
    def __astichi_param_contrib__Root__p2__0__P2(after):
        pass

    def keyword_only(kw_params__astichi_param_hole__, *, existing=False):
        return (existing, inserted)

    @astichi_insert(kw_params, kind='params', ref=KeywordOnlyParams)
    def __astichi_param_contrib__Root__kw_params__0__KeywordOnlyParams(*, inserted=True):
        pass

    def optional_annotation(optional_params__astichi_param_hole__):
        return timeout

    @astichi_insert(optional_params, kind='params', ref=OptionalAnnotationParams)
    def __astichi_param_contrib__Root__optional_params__0__OptionalAnnotationParams(timeout: astichi_hole(timeout_type)=10):
        pass
# astichi-provenance: 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
