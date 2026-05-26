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
