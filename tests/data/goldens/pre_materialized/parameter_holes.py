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
