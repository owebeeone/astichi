astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    trace = []
    astichi_hole(body)

    @astichi_insert(body, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__0__Pipeline():
        astichi_hole(__astichi_root__Middle__)

        @astichi_insert(__astichi_root__Middle__, ref=Root.Pipeline.Middle)
        def __astichi_root__Middle__():
            astichi_hole(head)

            @astichi_insert(head, ref=Root.Pipeline.Middle.Head)
            def __astichi_contrib__Middle__head__0__Head():
                astichi_hole(__astichi_root__Root__)

                @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Middle.Head.Root)
                def __astichi_root__Root__():
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.Pipeline.Middle.Head.Root.First)
                    def __astichi_contrib__Root__body__0__First():
                        leaf_tag = 'leaf-a'
                        astichi_pass(trace, bound=True).append(leaf_tag)

                    @astichi_insert(body, order=1, ref=Root.Pipeline.Middle.Head.Root.Second)
                    def __astichi_contrib__Root__body__1__Second():
                        leaf_tag = 'leaf-b'
                        astichi_pass(trace, bound=True).append(leaf_tag)
            astichi_hole(tail)

            @astichi_insert(tail, ref=Root.Pipeline.Middle.Tail)
            def __astichi_contrib__Middle__tail__0__Tail():
                astichi_hole(__astichi_root__Root__)

                @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Middle.Tail.Root)
                def __astichi_root__Root__():
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.Pipeline.Middle.Tail.Root.First)
                    def __astichi_contrib__Root__body__0__First():
                        leaf_tag = 'leaf-a'
                        astichi_pass(trace, bound=True).append(leaf_tag)

                    @astichi_insert(body, order=1, ref=Root.Pipeline.Middle.Tail.Root.Second)
                    def __astichi_contrib__Root__body__1__Second():
                        leaf_tag = 'leaf-b'
                        astichi_pass(trace, bound=True).append(leaf_tag)
    result = trace
# astichi-provenance: eNrtWltv40QUTptL06QtagMIdsUK2KV0WbWwIMQDAlR1d1Wpuxa0+8DLynLiSceOa0f2uNlKIPHC5WG0DzD8DH5KfwbviF/AGV8S2xnn6rRhN5HaKONzjmfO+c53zozmp+Kff+/mvA/NKw5htPTEUl0DsT+YJP3CjtmPbIcW6pZ6wZ6xHZyjhYfP2zZ/+nPwsHiuGC5i/NGBYhieovRrqNl0zYb3TFLO4kaXNZXRNXin1sCajC14J803yHNP+rGlqCB9l4vSTTmUcuyG3NS45K1Ty1D5748dopwiVa67GgwQW2mgvfYFc+q0ZGgmMi12tEwrDcuQrWbTQYQd5WgFmarce7rBf0YlKvhd/J5bpwXFPnVg3fiN7rTx2/RNuTsf27KILB97/xm+id/xJsy1nTp+/2gZ3z7K4Tvw/UFoU6HlFrroWLbqGRbKpIzmaPUReJNolvkANcE7O5L/IaGzTe5jfA9vg+wqzN09QyZxBJLVtuVYpnERrm/7GQT+XLHhN5NopdWJPKTVVkdWUVNxDeL9LrY6vlw5MgrzK/kAKe07jnZqxnGwQkAFkX5nFr2Icd/laPGEWDYKwy70YjHwIl73UKIBYmNARf5sxKEoxx1K18hFG0Hgz7ibmJTi9tUQ6fDO13pLwrXYQvCN/nfmA2t5sLYWWNtOOACXxHrrgd5muOA9Dy1Rk1tdtIhG7ydijj+nH/WA27BMYmv1ELs8v2X5E1n+VmsjnhgACfxF0sKXPlLw1xL+Br724e9Awg96wZ/cVVHHb6W4ir6VTLwnmqoaaGjqbcV9KHqXeLTfh/jFNTomDUO0gBHQpVh5PVDezM4JdEcApDAWfCoelA69Oc0hjCbj7yxBdDmHIBIR0azw8+FwInqk2cDtE/npMOKbx8nglw2kNGVoGXi4T9LdVI4WmvKBZUKbYcaKDV6HDgOM7SqMFlqaqXYrSDWwUQs8ICdLS21oaYH6vU+4Y1yCYpV0YOx77VRbcRw2YUX6bnBFiiVCjq4E7UysDud5g0CLdcsFt+B1fWUpl4s47jd9jQ8kJlTrq2U1/prEULc1A/dA06K028hUhyz1RspS9TxMQ6x6M1C9nV5/7wjrbzCK6IaKGpatQEsDrSZgGfQHRG4jjJxmOsgmbDJuS0tiEYnpd6NB0XeX+BbAhsYS4vW696iHuSwGEiWL5/toq9Q/5VMr91qT0ZVKflUaR6VwmF5LRQo6EmIo1X4xYLaR4psY9dNBFFC6YiPi2qYDJCRLtOp1tm1o6M8E24wxK3uUme/L8gnA2lSzp+YwGUci5SSjBFRcZ11myYaI+1GcnsP6rVQ2yZJzBXmr7/E3z4BmfYR/NnRd10Gw+ldgeyCp6g9HTc2piHRHxKRFKInIFtS+o6UYREfqoUQhP/ZDPnOmHpPfdDyeeGs8cXM88TG5uRRy22TkjFJAop97AZclveNDVig2Y0BfTtUZZAi3VxBdo9fxuYDKX9cElZcBGVmHesbHj7RAFM1gV3cGOejoiE/F2/w/9eY0f0dH45Do4oxouvX/O18bDL3KaWCxuVhsLq52c7Fo/bsHM0/FlSqj5l93rq3E97Of/gOfzHwR4O8LAlwQ4HycruiXwogsjlam2eLk8zM8WtH/mZxdF8cqC2TN+bGKaPPbx9bfL4+oej0nK4KJDAJHqnhrPHExOEY4Y+gvqwOiLRCbMTG8uBpimMu0/38lZtoVvCmz8mpyLuusGHx7pmQjxzWI4O5MITBVAFOl3t2ZYW04V1sN1Dai+4iovY0sE7aShoJ7o93fHYyCcdNx4I1fJWV4SNJUwhso/v1W7dS0IGzeHd29/wBMQ7G/
