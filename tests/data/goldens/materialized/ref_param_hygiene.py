from types import SimpleNamespace

def consume(class_name):
    return class_name

def generate(function):

    def wrapper(cls_ctx):
        return function(class_name=cls_ctx.class_name)
    return wrapper
result = generate(consume)(SimpleNamespace(class_name='Counter'))
