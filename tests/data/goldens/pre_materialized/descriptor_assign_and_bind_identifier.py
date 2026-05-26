astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_keep(shared)
    result = []
    astichi_hole(cells)

    @astichi_insert(cells, ref=Pipeline.Root.DirectCell)
    def __astichi_contrib__Root__cells__0__DirectCell():
        astichi_keep(shared)
        shared = 10
        astichi_export(shared)

    @astichi_insert(cells, ref=Pipeline.Root.AliasCell)
    def __astichi_contrib__Root__cells__1__AliasCell():
        total = 20
        astichi_export(total)
        astichi_keep(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total)
        astichi_export(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total)
        __astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total = total
    astichi_hole(consumers)

    @astichi_insert(consumers, ref=Pipeline.Root.DirectConsumer)
    def __astichi_contrib__Pipeline__consumers__0__DirectConsumer():
        astichi_keep(shared)
        astichi_pass(result, outer_bind=True).append(('bind', shared + 5))

    @astichi_insert(consumers, ref=Pipeline.Root.AssignedConsumer)
    def __astichi_contrib__Pipeline__consumers__1__AssignedConsumer():
        astichi_import(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total, bound=True)
        astichi_pass(result, outer_bind=True).append(('assign', __astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total + 7))
    final = tuple(result)
# astichi-provenance: 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
