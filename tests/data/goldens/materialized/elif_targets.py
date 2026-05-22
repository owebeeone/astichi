def dispatch(event_type, payload):
    if event_type == '':
        raise ValueError('empty event_type')
    elif event_type == 'create':
        result = ('create', payload)
        return result
    elif event_type == 'delete':
        result__astichi_scoped_1 = ('delete', payload)
        return result__astichi_scoped_1
    elif event_type == 'manual':
        return ('manual', payload)
    else:
        return ('fallback', event_type)

def nested_dispatch(enabled, event_type):
    if not enabled:
        return ('off', event_type)
    try:
        if event_type == 'base':
            return ('base', event_type)
        elif event_type == 'nested':
            return ('nested', event_type)
        else:
            return ('nested-fallback', event_type)
    finally:
        marker = 'done'
