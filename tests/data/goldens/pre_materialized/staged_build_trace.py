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
# astichi-provenance: eNrtWt1u40QUThMnTX/RtrDAVgi2rbQpAhaEEELiR2VLtaKsgV0kpJUi48STjl3XjuzxdouExAV/Ws0d5gm4gUfgCfYluOCGG16Bi+XM2E78M+skrdMmZSOllWfOnDlzvnO+cybJt9Vf1hsl/qIV1SU+rd2yNc9E/s++LP/g3/a/8RtUatnasd/0G7hEpY/udx02+304Wb2nmh7y2dQN1TT5QvnHaGXHs9p8TlYPk0rLuubTRdhTb2NdwTbsSSttcp9Lf2KrGkhvMdEWrZm6hSzb3yvTeWRpSuyxbZuK3em4iPh7JbrMZuND816LSqqz74L1+Jne5vh5ellRor0d2yaKcpv/9fEafiHYFr+0V8ZX4b2+V8IbTJVK6wfo+Mh2NK4vM89H2BMbDUZKdGEXXEB029pBHThSQw5eJPKQxRyDt/AmyM6Bqd4hsogrkFzo2q5tmcfRcTabgNY91YFnX6bzB0exSbpwcKRoqKN6JuHP1YOjQK4eGwX7agGqtW3X1fetJHizBJYgkvVdlThqGzFXlWj1DrEd1MMq5YIqOA0vcUR1iK5EUKHAiJTD1/fqfffRRXLcRYDoIXOKLwscPBcFImzzVN94vJowGV9JbFMJlVRAySIo2UydENdAfD8UXAoFL7GzvMJxj69f8VqCkesp9PCb9OV+xLVtizh6Kwo6ll6K8rqifKZ3EQtuABe/ldbwToA5flfG78G/D+C9LeMP+zCeyBXxEF4RuII+l06UW7qmmSgvVVb6nkqrTwIo9hR+cJbH71sjigQqYQRUBGt+DaWXQulL8UMmjzTMIWlDEA6Ra9mePCBu8s0nJxhGZs3ThsLDyQkFTgp/FRwF1waTwq7uAHWeyA+7sbN/nMaybiK1oxB1n6H3udAN9Yi+6zdsyyWqlaBwvASVGXS8qvpUOtAtrUfQC+H6VTCkmWbt1VzWhiK4TZgfPIIS5SgXyn4j0VVd1x+N7D/Fa8azM6VSiu97oVuis2HZTxSwCiuotNqyPTg5WPeof6afuKqr4dbBkTMjasq2Vd6rwNmhrKvdLmJaE4ZFgldEh/g3KbsWym6Ii9ZmpmjBCKLLGmrbjgoVHXosCDpYl+Pz5cjnuuUih/gjUQnPpnzOMF6E8/SWGBszrEl1oIvCS8Yin+rHRhEDKeJnaZg80wwYORMaWfJaRoNZVO8X7YGytYDgh5CUboZlJ1/O+JJBPlBbNeSQpGAA/kwgKMIgO0RnHUQ8x3Ih1ZsyXeDtWRd60MNeR3yiwhenvDcU5Q6EoaUVz3ksS/Kp7lGW3Vq+IbFIOTW3ZQPu8cllXE4DOxSN+Y+nMUE2GZtMvBDmCqJxixsdt2IgZ/mn5CzjOijI5Snj7bQrC+CmhoicqlAikJOqBZBg4t4nMSJCZ4ejM36qG45EjLtDSTWHkvpqKKnhyK0WscVI7IYEwBqY53lTNvQgqDJ8Np5we3iSUlhgeExtNJyggp0Xxr+fLcYTCOlYwBrP5z9UIqpusvb7/XKmoJ72c6C8iz/bll/6vuD7T8zFfwiKuiA3fOPrAPECL/n4n3NuZI0KS8mpaWJ/K09CExuzYmATG5Odpib2/9V0Uikg1WLaTgOdVYXLEophsb3PmVO+mypOeboyCZwSs2Igp8Rkp/1ibPyRceeTW7FA6u9yYbdi48+R6enJjfgCRMLk3Ijj1CjC2Ngp56+4eJdiAappvDI+yA4J8ErdOseTkw/GmpNnis30ZEmq4p4yRQpy8liCNv/L6pqDXM8kya+qpVCDBBpqQYuabvxidjPpuVB6OepR4yqWC8iceRGGW7k/KsvHcDTIROqzQwNieZ59FRz88krft2zwPP+t2Gv/AWZ4BME=
