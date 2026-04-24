astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def collect(**kwds):
        return kwds

    def run(params__astichi_param_hole__):
        values = []
        astichi_hole(body)

        @astichi_insert(body, ref=Root.Body)
        def __astichi_contrib__Root__body__0__Body():
            astichi_keep(pinned)
            astichi_pass(values, outer_bind=True).append(astichi_pass(first, bound=True))
            pinned = astichi_pass(first, bound=True)

        @astichi_insert(body, order=1, ref=Root.Body)
        def __astichi_contrib__Root__body__1__Body():
            astichi_pass(values, outer_bind=True).append(astichi_pass(second, bound=True))
            pinned = astichi_pass(second, bound=True)
        call_result = collect(**astichi_hole(kwargs), **astichi_insert(kwargs, astichi_funcargs(a=10)), **astichi_insert(kwargs, astichi_funcargs(b=20)))
        return (first, second, values, call_result, pinned)

    @astichi_insert(params, kind='params', ref=Params)
    def __astichi_param_contrib__Root__params__0__Params(first=1):
        pass

    @astichi_insert(params, kind='params', order=1, ref=Params)
    def __astichi_param_contrib__Root__params__1__Params(second=1):
        pass
    result = run()
# astichi-provenance: eNrdWM1vG0UUdxzbcew4JC1JSduQIEKTon4kSBQEB1oKCMmtVQUOIKiWtT3p+CO71u66aYQqOHIYcWH5B3rtrb0hIaSWCwcOnLhy4IiEuPYCb2bf7nzsxk2qVKqI1KT79n3+3pvfzOzXxe9/eSEnfti47QchK11128M+Cb8LT2+Gt8M1Vmi67d3werhGc6zw/q2BJ18Vb9r9IQn5i8t2v6/YbA2dlpA37G3FV77TDtkUxOm0aMeiLsRh463gllC94trtWLXJSv2OQxw3rOdZhThtK34cZ5WW27fcrS2fBGE9x6b5W1X03LDJCrZ3w4ek6ZEoMp1j85YVB/ZcN7CsTfE7pMfoQhSTnqzn6WJ9nL5Yz9El7sdm5R7Z3XG9tnCWei8k/IlLI0mOVT+A4oOO67xHthRIHI4EXaHLoDIJ6Q23iRP4UqE6cH3X6e/GmS9fh2bctD14Dhus0ttRXrJqb8dqky172A/Ec7G3E+mVFSlkU+R9exUxOMsmAKc+aQXgnZ5H6WtRLPp6g16AP2/Cv7conwbwlyQnnlihtwNAsIrtOG5g8xIh4lSwOyDQgG1eT9hASKYBkjxAcgSSeDtOBdyWNkkw9JzEM63KFtErWi84zlUF2UhSkBKbTbdJy/XswPVgPmB6AYkJTwTwIZNGg1VFcgNAcTvpoN4vCc64N3SygPkQn+vsZORIDpJ4FnPMB+kqDwkhShCiDCFKEGIF0tSgbUg4+IoqXfL9zg2JB5sIAGoSGMNbEivN58OaY8WPoOBkVXFgJhCYCYhY4RGrYkFxSOQAkmgqNIy5YQ0NORoif9UbF5aTVtXwfzNK0+bB4VdgVUarMljNgNWyWgAtKlqzqDXHM10VXVGN50WvTYns0ymJf8t1Aq/TjNcyZyrLWresdzllPWbGtUaMLFEyVo+QQZowCkgIY2bVrDToOA5pjzSJITA9yVEtoCQrSeCSSwHHYBgQdVGNLGNg+76ZUxSKL9mpVPMC0L2PWjXUOhpnnmMTyJEyfp1VXEjIs5odB6rn01i+7Dp+YDuBkuU3wChcISaNZfS9kpQ/JyW2keYrguahdqBJezAgjoD5vqF1BovJmtx7qK/SSmpyWXGr48E6UnRnUTeZ3x+SsotNdxhV/FNSpLBaxChL9VWkMk1iG2msqnOhT0Faso2hBlrT7kDGN5MGF9GmCDaliCH2gmRBM5pEo7nUVPwKun+g1jxqHU9BQn8zwSgKXe45ak9KYhuhz8TEpBYBQkI/ze4sm44nveP4xAv0WS8LVomgn88kqj11zXaPe7DFQ31305sZK3BO0iOPgbcxXOI5iPyQFSKm0pWiIsdQKSOJDNFnYu/5PJNM90+dG4dEnXdH7hj3DkY93RNjudxe7CPn7Ed9zh48KanQh/RnPeg+uSQ2GU0nJR+OLIKrVP29KSW9fv6PZNI9y7E41n0nguTZoxT696FyyJq6Z8DWSTxtz4DFn46RlkhEHmWTEP13NP908wL2g7APOSj7ZA4Uq7bgwmh5xIe7Cue/HbCcRMtJPN7vMVYX8SjJ1Y+g+gL2QIe28ZgjK/dwEj2spVequFOJg1KsfBqVz8sVpfpYF4BxyXFF8th09NGaFKbcRWS+zEuSC+VLs2OmftZ+OBOzPr+Xx0VlU/CMRFKZ0TFbn88KHljzgruW6hcTLplFPxfT5HqJT49E7biB2iJ2dKm+8Uyg1v3WNNoHTk0dp+efNk7EWAgbMbGpi4kLNxN2gAvkx8OB8omH3tbAEgc7PvEVcDEFLirgYhZcmGydKB1FpQVVSdwaYo0TqPGS5qanu3kZlc5pbu4oGuuocYEXLsVVFL8hEKpg5SiJKF1lqBJiHZvI89G6ebU3Tknx/R/0rkXfFEZ9LwAg408CeUSJt/dU5icBjfyTw8sq2gA72ck3lMI1fn9LuscLWhRV56KC7H1uYoZZ6u6KFY4wMfcy+kCdfukiHSst0TczJY9rGXmYO1nKHclK9nCHYGNfQxCtlcOfg+7v4PepTkD3T5P/DtT97l/RWe4Ane9+wk3Mc9ATj073n/Tp5rDHJvt0U5IHG3lqrqFpbfSp+Qst4xoeWmvK7SjaGtQ30zHrqzGm93+cNT9r68fZlZGfyI2z+aMDnD8znGWIVPiNr7cEvz53bjguQC6+eZ/7D0Hj02k=
