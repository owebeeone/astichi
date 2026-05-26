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
