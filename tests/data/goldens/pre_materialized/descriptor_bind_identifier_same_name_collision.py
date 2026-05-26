astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_keep(shared)
    astichi_keep(shared__astichi_scoped_1)
    result = []
    astichi_hole(cells)

    @astichi_insert(cells, ref=Pipeline.Root.CellA)
    def __astichi_contrib__Root__cells__0__CellA():
        astichi_keep(shared)
        shared = 10
        astichi_export(shared)

    @astichi_insert(cells, ref=Pipeline.Root.CellB)
    def __astichi_contrib__Root__cells__1__CellB():
        astichi_keep(shared__astichi_scoped_1)
        shared__astichi_scoped_1 = 20
        astichi_export(shared__astichi_scoped_1)
    astichi_hole(consumers)

    @astichi_insert(consumers, ref=Pipeline.Root.ConsumerA)
    def __astichi_contrib__Pipeline__consumers__0__ConsumerA():
        astichi_keep(shared)
        astichi_pass(result, outer_bind=True).append(('a', shared))

    @astichi_insert(consumers, ref=Pipeline.Root.ConsumerB)
    def __astichi_contrib__Pipeline__consumers__1__ConsumerB():
        astichi_keep(shared__astichi_scoped_1)
        astichi_pass(result, outer_bind=True).append(('b', shared__astichi_scoped_1))
    final = tuple(result)
# astichi-provenance: eNrtWUFvG0UUdmOvE9tJKkgDtBVSS9MoqBCIACEaCZSkcDFYVUHqqVqtvePMrjc7q511kyBVQkgEDnNBDPwN/gCHHkDizJkjdw4gDpx4szvr3bVn7Y2bhFRqpMSemffezHvzvW/eTL7Qvr9+tRT+sLJBA86qnxCz7yD+HW+1jvg9/oivsUqbmIf8AV/DJVb58MDzxehXclB7aDh9xMXQjuE4oWLr61iz23c74VjL2MsanbFMzuZhTquDLR0TmJOVO8FBKP0xMUyQflWIsuf0WIr6Hb1rCcnbu8QxRfsNE9GOb3kB8fW25Zq6ZSI3sLoW8nUKc+qu+NMhjmNRi7jr3iGnbVZ1LBe5hDdnWB3GdNLtUhTwZonVEdhIRhdFMy3RwNfw9X6bVQx/l0JM8PLAJXyZXdEHa/UJCXT9ruUhYU3XOb6KXw4dEhZoG7/SnME3miW8Ap83Y7sGm+uhw33im6FxpUxOb4k1PoJoB+DlHdSF6K21op8g3gwRCo5v4VWQrcH6+3sQKqqQbHiEEtc5jH1cfQDAeGj40OYtVu/tpwZZo7evm6hr9J0gbGu9/UhuLtUL66sKANVi3OAFfDEBCl7KxnGAix5CnjJyKzIGif+rw5tRpdjwkVlM3cDrMt6jltXxLuYKvjvl6l+KVp8AinaIB+2N0/KnxKpblFq7bjaFZwPYTRSMYr3qIwq7K5ZTYtqnkIAoTlklwqvxwhbCDLeAbTIkgyKkqNOkll0smw8OPZHWewLCvPVkW3RldM6ytFYGa/N5W6R1kONQrtZekNrPZ/cjbXhpsB+q3o2hrMTvsLUEDR3iBr7V1vV7Ic+EK9H1N3V9B75tQcrid4f1N6NMxu+38AfwsQW/Oy1857jJqUb0aPCHw4XvF2PAAXCLEh9JLZWOIYHPC2Jzboe4NDDcDD7xQrPOKj04YQZoG8IkPnoyGLLFeG/RgUf8gI9H5WJemB+r9S5KveV8PL6gxKPsRWzRRB3iG+KkdUT2gn4RbyyXooneLOV580MhvcibEpuVh2eGWcriOGJlHw7FcH9rW4FInX6AMkwHY/9kWhl35uKTvJgjUB/AJJxVRHoWU7HLF6AK02T+ForWUK+Igzo8bNZHQd93KYD3qMUaIXt6cKDvyTLjpAhoIyKg7XNJQPb/QEDhpMWY5+c02VzCv54Sz+DfpiQW+5SIBf8+lknwH2dAHX8min/hv0eoIJ8Y7BJkbfH8tivHEo/oYPuk6cCug23BBHYDvuQSwPTlU0Vaq4wrn2pAIRTuIL6qhKrIEqqSACVGVtr4iwPXVb0KBntbwWDJJW2woqiUkq0zL6fK4UZERfvmMcophV6SjqMms7u+OXHXs1lQ5PrmGZTy6aprfDC+rs5NX1YncLRHrwF8iFa/iVhV2Lkm7axkgrGc7R1OoJvp3Kwanodcc4J/r6X8g3z+rO9lX1fwlwIr6UWyCwZP1rku7WxIO5MxcKP5ltR5L2ZYpdTrUup2PnGPRco0xK3K0uGdtx8pOVKhejrcrZhoHHfnibNaij8KBWKoN4Kfym0Ff2fE2OXsq0H4jBK+hFHw+/63/AT4cSPhx+1zyY/2ueVH+8eJRcCJs6L9k5jz9NjQfjzRpxQT2r8IAI+jwHZRCrSfUeBTQIHbZ02B9r/QvYbtAdeNfSXSupZrOIpHIk3a1MCmllzVxtQ+WhCe8KPuClNz0tTCMdJb6C1KvUtZnKZNLqdvh+llL08P1UK36lvHuFWP4LQAFgvfw42cbgVUMmIxVJKDEcn3ZWvXJT6K/n+x/h9FdM1G
