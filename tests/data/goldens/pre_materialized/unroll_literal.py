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
# astichi-provenance: eNrdWM1vG0UU39hex4nz1Uh2BCohqqomRWpIjEAFDqgUqkouFmpuoGpZ2+PMxuudZT+SWKIC9QRixIXlD+CSP4ALKidO3CvuSEiIAxc4ckHize7YM95drx01NRKRrNhv3pv38XvvN7vzmfrN71Ul/KN53fUCWnyPtH0TBV8H1+8HD4MdWmiSdj94EOxghRbePbUdsaQe66aPArZwWzdNyabjW61Q3tB70l45ox3QJfBjtLChYQJ+aL7lnYaq94jeHqg2adE0LGSRoJ6ji8hqa9LPFjE10um4yAvqCl1hq7Ko7DdpQXcOXQgar0eecYU+r2kDxw4hnqa9b9iI7appAd7Az0V+8eV6Dr8An826gl9ke+m01EX9E+K0ww0T66GE/WLSSKLQ8h0ogGcQ6x3UkcpisWrgq3gLVBYgRL+HLM8VCmWbuMQy+4Potx4AIMe6A7+DBl3snkiLtNw90dqoo/umF/5WuyeRXkmSQjRqhF3xlusah5ZwNu+BOvJiZSqi4zAmKIlC1QOPOEP84qkWoTi4HEJnQOuINFHkO1bVzfqCqBFd8vo2Atx6rARBI6WKJR5TGS/zb2siTlwd2T3PbfNguwS2W3JOWAXdD7jWMte6xILfDgGVjdf9ZorkJb7VDXpNdFGLWJ5jNDXtfthObEw0bU/T7hFiA3T4ZW5Ui4DErzbwa/DvJnzeaOA3BTaZidKVgT+jZxPHS1Z1ULOVRN53QNfhWqtcqzLIW6HzvK8FcnnWQHSR+B5ytKZhtYMQ39JtYrmebgmMcflzWugyhQFyV/j+14YTsSEkeizU7cTYbJ8T8ALYFsC2ALZr8cTpkmsySAyWxh6r2Bfc5BI3qQj05Z2qfjNFItB/JQV9QSOy07ATDjxk711cK+CPp8eevi5C1cPBh8gARDleB3UGzcuISdPE6H87rmv63MEnVG0SP2qQT4c9EWPHqt9MSuK9UE30QnVMLwBn3vJY0aE9pU6UCnQ2lhSK4aEA1kCoum0jFvkG/j6mtczLOMyIqh3DAW7DjxpcdYWrVtL5o5rgD5AgutJGLeLowKZwkMF+YJc965aL4rMeteTmsC1HZ/2rLN04dnmAPhrthQO/6bYcw5ZnG3+X+U3EWxo002ikc+B9jiOuQKSPaYG12USliDmzlVQ+VBlaVHVNo4UkGGEluVeWn5QKJkV03kGe71gukOBBg5bDE82G07rHnxTiRPJsCG6fFePvGRPc/pDg9v8bgmOH29HanKJMZCr8cJSjHj3jIytlUMKTeCwx4cf4B0jmSpRMNh8VXSASRl4JQqqmE9JGgpBAgvCP6QyEfzoH5fwzkXJ25PMCnjSQM3JewMglfSQlAsknYP3zeVkK/5JNKfjXCeu/TUNJ+9nE9Ucs66ciI5RW7j8ZCeG/Zkg8NUj56MOoa2fJPbUh99TOxT1vccW3Ew/Jd7Peb9IO6uE7rA0PV+NfdCqprNUXrFXlipenZ63r3OTGkJA2hUSPBbALSgfxl6vdCyauL6chLtXDhtN+2gepi+Cto49YvOegrqObzEDmrdz/h7dq0/NWbta8NS3c+bBDIsfrqW//Y3XjU/dk5qhEDT43rFkiwBSRXLP4XUUqy9Gig1zfDB/B745QvcLLzclu3OQXOKkw1dUBqcj2q5OOGcGZXYTszCu3GIBnmddznDsm38pNec2CTtOuWWYQX/rxdBY7nmKbj0dsosNppys7+auTkx+drmknKWWzFJE8CfH8+B2jcWgR6P7wMnT3X0E7Q3c=
