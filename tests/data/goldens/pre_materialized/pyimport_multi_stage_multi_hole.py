astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def f1():
        astichi_hole(f1_body)

        @astichi_insert(f1_body, ref=Root.Root.Root.Mod1)
        def __astichi_contrib__Root__f1_body__0__Mod1():
            astichi_pyimport(module=mod1, names=(a, b, c))
            return (a, b, c)

    def f2():
        astichi_hole(f2_body)

        @astichi_insert(f2_body, ref=Root.Root.Mod2a)
        def __astichi_contrib__Root__f2_body__0__Mod2a():
            astichi_pyimport(module=mod2, names=(a, b))
            return (a, b)

    def f3():
        astichi_hole(f3_body)

        @astichi_insert(f3_body, ref=Root.Mod2b)
        def __astichi_contrib__Root__f3_body__0__Mod2b():
            astichi_pyimport(module=mod2, names=(a, d))
            return (a, d)
# astichi-provenance: eNrNl0tv20YQx6kHZcmyXTtA4gRwUh/cxHbeMlK0KVCg6OOiRkWNXAOCFFdeyhJXocgoAhIgQIGihz0ECNNT70WvBXps+iV66XfwsR+g+xiKy4doF1GAGLBFzv45Mzs78zP1Qn/9Zl0TP7Rijv2Q1h4QOxig8FW4dxg+D3dp1SL2NHwU7mKNVr9+OvLiJf2JOQhQyBe+NAcD5Zle4HaFvWMOFV9lxw7pCovjdLFjYMLi0ErXfyqk3xLTjqQWrQ0cF7kkbJfpMnJtI7qt0OUuGRik1xsjP2xrdI2vqqZLgUWrpnc0ZknjczIyPk8vGEYU2CPEN4xD8TfEm/iSjIm32mV8uV3BV9oa/pD7MWn9GE0nxLOFs8y6sPA7bpUWjTa/YZv3HeJ+hXpKSVxeCbyDt5mkwdILhsj1x7GgOSJj4g6mUebbj9hhPDE9dh926PLxRFmkzeOJYaOeGQx8ca8fT6SurlhZNjo/t32owU1a7t1ljvFtMLRkGHyvgz9mH5+w3/sd/Fn8ZB2ETbwKV+txRfGFROl4WapQiHXmYDtR/aXeXUM0EnvmO1BvgPoiKzS+JuqrOpH1TVvizezFB9olru85VnSmEMsw7hgGa+cF7pmuRyFHU2c4Ip6f7h/ZDWWlCNfk7CxBJ8UnXuFHRmtDOXAsYBymOhRpb2IMTi+C061Z020oliE8OKI6b7Mxd6ZR/WEwSkwykn2xqwQqmWqUj8DnVeZT0ViqZhc0e0lNV9VcB82NwEKKeQfMN2ebuBJbUKp8twIrx6LR2iHyA8+dbYttdQpXzxJ7wy8y/VmHRmqoueMfmO4lKJqgWEkoflQUa6D4QO4tMi8prb8FjJhZEF2zUZd4pk88RjLGWdYXee21FrWX445RurkqAJ8qjEJiwvDDIq2cr7hNKh5jk2iSxhc+H53AR2pFf8u5UrqTj1kytxKLVwIwagLAzG2Ify8S4T9OW6fVBzAHqkiWtgSinL1mTXTJE10zZohc8acjxJAx5ABm901xP2KkHQLlU8xB+Gdm/rOD33TwX/BvIAl9lbCtd0bYGqRVm0PY1oywf4N6A9QKYVUnkrBpS7yZ/fmEbSUI2zIXuOmjsxF11sz4cQadLV6Ek/+HTjwpJslJESMFQ06yhESKOaLffoZ++1n6Xc/Qj1t+WiDy+npJ07LUQ8mVCGurGaytRoORd4a/pBr3MnRZHrj+KdKmwIV/PQ1Ob40cHfq5mDmZNHNMKjFSQ5ZFig4hajlIOXhnSGlAWo05SDmIkNL/VPZEA8ankaSK6kdSJW05E1UOklSx3huq4H9ZCb6XJVgcU1SPc1697DApS7JFXXmP8NK3eFqb/f5cwvQXTJiG6LQ5hOl/LtKZLy+GzJnRItFhnYaOTPAck0qG1CRl0VGHEAnB6TVLf5dNUnmn8HtxTsHOWqYcZzmmgrctBG9wzpFLPCS/6N76DwMxU/4=
