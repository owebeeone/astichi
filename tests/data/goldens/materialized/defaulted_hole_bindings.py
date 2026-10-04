def fallback(input_value):
    return ('fallback', input_value)

def replaced(input_value):
    return ('replacement', input_value)

def nested():
    if True:
        return 42
