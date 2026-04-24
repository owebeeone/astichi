astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    left = 10
    right = 20
    records = []
    astichi_hole(body)

    @astichi_insert(body, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__0__Pipeline():
        astichi_hole(__astichi_root__Root__)

        @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Root)
        def __astichi_root__Root__():
            astichi_hole(body)

            @astichi_insert(body, ref=Root.Pipeline.Root.Step)
            def __astichi_contrib__Root__body__0__Step():
                astichi_pass(records, outer_bind=True).append(astichi_pass(left, bound=True))

    @astichi_insert(body, order=1, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__1__Pipeline():
        astichi_hole(__astichi_root__Root__)

        @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Root)
        def __astichi_root__Root__():
            astichi_hole(body)

            @astichi_insert(body, ref=Root.Pipeline.Root.Step)
            def __astichi_contrib__Root__body__0__Step():
                astichi_pass(records, outer_bind=True).append(astichi_pass(right, bound=True))
    result = records
# astichi-provenance: eNrtWM1v3EQU92Zt70eyIQlJEaBKpA1tgoDyIYT4EgqFHtjWQCsOVKos7+5sxl7HXtnjpjkgcaDAYW6YI+fe+Qs4c+bWMxw5wKEceWOP1x7b9e5GSwmIlTaRn3/zPn7z3pu384Xy3fdPSNGH1g2fhFS95g4CG4Xfhpr2VXg9/DzcpXLPHRyHt8JdLFH5gztjj729y18qtw07QCF7ddmw7Wih9nWychg4/eidZhyKSpfMQUhXwKbZx6aOXbBJ631yJ0JfdY0BoPcYtEdV23SQ44bdJdpGzkDPPPZdW3eHQx+RsCvRVfY2K2oFPSob3oEP3uOtiXH8JD2j64ltz3WJrl+P/ob4aXw2Nouf6S7hbfie60r4PFNl0OYIHR+53iDSV3gfSdgTk8YSiS5fAQqI6TrvoyGEtKvFH5Iw5DBi8B7eAWwLXA0OkUP8EuTy2PVdxz5Owtm5Bbt12/DgOdRoe3SUeUmXR0f6AA2NwCbRszI6inHNjBT8U+NdVfd93zxwxM1rEFiCSJE72UZDwpiSqHKDuB6abFWOARk4wx2ANS+7jk8Mh2RTAHe6bSqPTGcQanxhI6WOrpDjMYLdPGSETBBZcq+kzuIP804qnnmAIy8/mfhW5wrqoECJffs0684m/kzjsCaHtcHOTS23tj3NeMND/ShNBPMyVyGDikZCjXzV9IlYbijeHiEV2do2X7uS+JRVyIStpCpB82MZ/x4XvMNPCZoVrkThSnZywWAV4F9yYIcD15n7z0dFkF2/EfRKJJdyqYxfpc+l5dd3HeKZvaQCWa/R9Zd0/WNzjFilQ6bj1/Ia3ogLAL+t4Xfg37vw3dfwe2lOn4iKbD1vlFAxf9fYSHnKKxfzuZwnfO9RBp9689A8+JEDOxy4no1PjGaW+OiF6Xlwg6DxSXKgggXotPuEGQsIEnpeJV/paTU2fD+cjzwX4L/myNtMyJNogx8sQiOos5ZN2y546ek91idzDeubuF8xndtc57MT5s+kEiPn4YXoWAQG4AQxxmPENKfuJagXeBwVGfQLX8aao8yb41pZ+B9lgOscuJWE/1uK/J0qPTdIIr2bBsqWbnM757sXg15RYuQcuVjMTYasCbnJJQZdHbCWbcBxBvMFdOTKwOlqkgqm4yOPhHO1kaiSpvQLgZO6B7MDMHJfyNSqJ/G8ZhUlulgDmzVuUwIXH9Bm2m8rgdalmiRN0SXHNSuCYr5rHFQSdlHEzlESeI4Px/9NjS5HE8EYRp7DyQAmdBhkdcC5yp2ztvLuT92te/PtlnWOWZh9e2Yg1HplOqREywkYt94ENYxs662YycVwrETTwMwVkYPPyvECWM1TVvCkKCqhbAED0MuncgCapRb+G5OO9QNLjoUOO/inxU4x92ecW6JTer5Rxfq5GP1mWSHiPxY3kuAH+E/R9HyTSLJy6jDSE7GV84jVjDvNIx1G/pZjTF38MfZPHGp5yOun+dz7f7b4V8wWu7mfIPBDDHm5nyAQa9FWUXIaphR0siml8kZL9ZAf2Ln7NJVrUEGDGl9oFX70nhXQLY5eS66wsirWFlBlrbIM2Ku81X1olc23UyWKi6IpNQAQxC8+zQPHBc6ja9oX/wKGjp3O
