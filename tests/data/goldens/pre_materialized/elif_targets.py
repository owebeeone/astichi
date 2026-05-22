astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def dispatch(event_type, payload):
        if event_type == '':
            raise ValueError('empty event_type')
        elif astichi_elif(branches):
            pass
        elif event_type == 'manual':
            return ('manual', payload)
        else:
            return ('fallback', event_type)

        @astichi_insert(branches, kind='elif', order=10, ref=Root.Create)
        def __astichi_elif__Root__branches__0__Create():
            astichi_import(event_type)
            astichi_import(payload)
            if event_type == 'create':
                result = ('create', payload)
                return result

        @astichi_insert(branches, kind='elif', order=20, ref=Root.Delete)
        def __astichi_elif__Root__branches__1__Delete():
            astichi_import(event_type)
            astichi_import(payload)
            if event_type == 'delete':
                result = ('delete', payload)
                return result

    def nested_dispatch(enabled, event_type):
        if not enabled:
            return ('off', event_type)
        try:
            if event_type == 'base':
                return ('base', event_type)
            elif astichi_elif(nested_branches):
                pass
            else:
                return ('nested-fallback', event_type)

            @astichi_insert(nested_branches, kind='elif', ref=Root.Nested)
            def __astichi_elif__Root__nested_branches__0__Nested():
                astichi_import(event_type)
                if event_type == 'nested':
                    return ('nested', event_type)
        finally:
            marker = 'done'
# astichi-provenance: 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
