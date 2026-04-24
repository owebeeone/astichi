astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    events = []
    astichi_hole(body)

    @astichi_insert(body, ref=Pipeline.Root.Loop)
    def __astichi_contrib__Root__body__0__Loop():
        astichi_import(events, outer_bind=True)
        astichi_hole(slot__iter_0)

        @astichi_insert(slot__iter_0, ref=Pipeline.Root.Loop.Step0[0])
        def __astichi_contrib__Pipeline__slot__iter_0__0__Step0():
            astichi_import(__astichi_assign__inst__Pipeline__ref__Root__name__events, bound=True)
            __astichi_assign__inst__Pipeline__ref__Root__name__events.append('first')
        astichi_hole(slot__iter_1)

        @astichi_insert(slot__iter_1, order=1, ref=Pipeline.Root.Loop.Step1[1])
        def __astichi_contrib__Pipeline__slot__iter_1__0__Step1():
            astichi_import(events, outer_bind=True)
            events.append('second')
        astichi_hole(slot__iter_2)

        @astichi_insert(slot__iter_2, order=2, ref=Pipeline.Root.Loop.Step2[2])
        def __astichi_contrib__Pipeline__slot__iter_2__0__Step2():
            events = astichi_pass(events, outer_bind=True)
            events.append('third')
    result = events
    astichi_keep(__astichi_assign__inst__Pipeline__ref__Root__name__events)
    astichi_export(__astichi_assign__inst__Pipeline__ref__Root__name__events)
    __astichi_assign__inst__Pipeline__ref__Root__name__events = events
# astichi-provenance: eNrlmM1v3EQUwJ3sR743pJCtmgJqQ9QmUglJKg6VQCgUcmiKS5pzZHl3ZzPedTyWPc7HAcSBQg/DATASZ04cOPEXcOqdCzdUbkhc+AcqxJvxeP253mzbkEpEihLPvHnvzfv4jT2fVb6bvKSIH1bSXeqz6kek5ZnI/9ZX1S/8+/4n/jIrN0jrxN/zl7HCyh8e2w6ffSAnK4e66SGfT93WTVMsVL8MV7Y9qynmVP0gqXTUaPlsGmwaTWxomIBNVmrSYyF9l+gtkF7hog1WNQ0LWcTfHmWTyGppsccmMTXSbruI+tsKq/HZ+NCU12Bl3dl3wXs83zOOL7EFTQttO4RQTfvYsBFXrGk+voxfC0zjK9uj+Cr8Lm4r+A2uTmfjXXRyRJyW0JmZFyP8iY8GIwqb2oIwUINYH6A2bGtZDX5oGCWLBwev4CWQnQB3vQNkUTdHcsomLrHMk3BLS3uQsUPdgWdfZZPdo9gkm+oeaS3U1j2TiudK9yiQG4+Ngn/VILPVTdc19q1kAscoLEE0G78qOhQ+QqwUVtmlxEG9hKViUIWo4RmRVgNKLFFZKPAiFfHF7YkofmyantgI0nrAo+KrORGeCKsRzMxG3uOXEz7jhYSZklRSAiXToGQptUVcBfF9KTgjBef4Xm6IxMfXX/AaOSNvpdKHb7JrUdk1iUUdo6Fp90X98R7TtDVNu0uIDZnFb6dX3woSjt9R8bvw5z343VTx+1EOTxcGVgs9MA5s4tBs8MPQ1vKicg/EH0jBWSk4H0ZFYWOyOxJpLvG6Y5PEo8jRGobV8kU9jN8mlkt1K1ETeOYhK3e5TJjpRWnlWq+7LkYjesrn65kWvP60BVIGJWVQUgYlL+WEgk27Js+cwXe1xsP4g1w1J1fNR9USV1b3GjkjOdVyM6daIk7FrYvK2aXIXjvL0sGfD1Ur7Fbkvy7gAu5CxuObcFA77ABOQU2LuPJLvyr7KrLxNas0iBcUlB/t4WEKzHWvkR1Jl049Uzr1wtIBVm9SnhQo6wQ1QTIRtUd9uVMV5xMoAYzrto34Ri7j31NSMzK28SZhlbbhAE3x96qUrknp+XxE1TOIghHEai3UJI4O/IZjFfTBulOhw3JRGh1BMS/2CjqDjh+LxHNSW4LiCEgxses13KZj2DQd6N9O/ZTYyHhYgcktjIBPI7JCFNjCY1bmtTlQKGB2sVBFtmeBFKu4ptFEfryUYS6rrchSTmSzQ2zMQdRzLBcou6eyKXHE2vAicSBfa9J0OnuCrkNoOjdGFOW8ILreg+j6CwRRfuB27gRhGUhD/I3gYOwsDfhw5sdo/1YTLwx96Ycf4z9gf81gfwOhV3WBVhySGerV86l3MUM9GEH4z0LM4b+H4lpng3s/CG3LqWML3pGQkzq2oI+z5rIjiYw/ARX/PAckdmrpXWQQ1pkbLPLKQJEAhOuFIOwscDXpyDwTBVFOXjpXwAwHYOcq/HNO3Nvg3PvpHLm30ePextNxbysWlzt53ws7Rd+FBa8bvesBG14f+38kzvfD5q8RNutS9tVhsbkiF77ZI+Lr0Yie8mQVhPbSX6irZ0nOv05JzgrFhtN61tfF5wzOn4cHZ+dTviZJzdH/DTU3hqTm6PlQc8g6KYkKC7y40O8mpq94Tjs/eSEyGLTOSC+0Gb+zQzmhTV8qFcGWVR3keqb4XtlJnEaKTI5kbgFmyhJnXHo2xFlcxeypT8WI312E7MJr1WzOHxXewkpiDb58HfZODB3n3Yn9N75uRTrv5JnY6W+iMKUDLQ/ZrwPjsTI4Hpl+Ha4nc7Rmh3K6Kb1xebls7FsEWkfch6/+C615Ml4=
