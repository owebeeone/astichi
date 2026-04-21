class Holder:
    pass

def run(value):
    value = value + 1
    return value
alias = Holder
result = run(1)
