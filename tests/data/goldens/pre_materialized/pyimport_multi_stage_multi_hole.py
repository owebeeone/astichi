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
# astichi-provenance: eNrlWM1vG0UU3/hjE8dJ2ggVNXyJjzZyYjDEEeKAAFUtXEz3EPUaVmvvOG8Te8faj6Y+VEJCUA5zgkHiwokLnPg3OPIPVPwDSD0CN2Z3Z+v9eGuvEVVaYSlx5s17M29+897vl93P6999dkUJP6xquB5n6m1q+iPCv+Wa9hU/4vd5i9X61JzyY94ChdU+vjdxgtkv5WT9rjHyCQ+mbhqjURioPYgjh749COc0Y5xetGKZnG2IPa0BWDpQsSerDrx7ofen1DCF917gyrb12Mt1BvrQCjzbJ3RkBuO3J1NrPKGOp4/9kSdcPOOEyL+DRTuTKXf7TB1ZNrEp71XY+oCOdDocusTjPYWtE9vU49kq2wqGSY8deBVe8/usZjgnrgABrjw+A+yw5/XHyTmUerp+FP7m8CK8HGYfRLt9eL1XgTd6ClzrVeF6vKbB1s7I9Jw6Zrgw6lNgVVjzEwGtZ1H7FhkKqFpa9PFi5O0AcGjDrvBtiNz9MbE9F/FsTqhL7dE0Pt/usaiCu4Yjxlxj62fniUnWPDvXTTI0BL7huH52HvmtJawiPzWoloPMVvAuqwwPxA7wXnbm/Whj+FCDj8TXDfFzU4Nbx1yeN1yvERcdbMKlWZXBc6k7gRfy4FcFhDUJ4WW55G72LleHB3pY6Xj8toy/Ki8POuGdJZee3RlmReDYm5XPgNqeY/XjCpK56Po7ui5acknUlkOMXY6TiJtpTv1WMhB2Il5YlZWc6vFqUBtMHUeUInJI7Vobh+dCd7oqd3op1QXbGesXs+UesHpQ8W6wi8Lqd/xJlsRIVJytdBIrRkEG1+Veu3KvdFS/IKolo/bQqEFBVFtGvRlFEdzrmvR6K4XJK2kryVxVJ0cjSavC1CPi+Y6dYHQB4Aw2+D6LGPyAt8earPYGcnL4EY9pypgNLOZnPGZLxlwqxCrwWs00e2RV0lbCtkwyoI7hUUdIgJA/Uc9z2mQrbhPLdgnaJFjbZ3kGBqXiIn5JVXjVEVQf1nfjhheQhe+RlN6Kud/njNLdF/BMuSMI7RPbcfij3IEflXZktds4BZQg1QAhHDi26oQ17QpZ2vCmEyK4dRyonxg3w/FEqNtYai6yAoFfxdSfGvylwd+FwoyqW/ci1E2VR1Dnq1u3SN1USa1qXt2SS88uArMicOwXq1s3pW5d40nKG9xfUs2STQdfY7LV/c9kC775F3y7SJ8wvkXUaYHO7KM6s4/rTBvVmdj6y8WLywKh2ESFYjNJCHMq7Lf5TVkkBac7K4pSKjSvBvBwCbbHGBlL8FFpR1aXfVvKPWONuBs9ZpJ1EYc8NdfldamLqPnwIqi5IY/QmE/Nh0XU3JD00chTc3LpGc6YdTlqPkxTc//ZoebTD9B2eoqIma2Y/H9EzacP0Qt5CtgZa5McO/+EZo+ElmLnRXyMpSRpts/LuWesEc2i+SYZFHHI0+yaxD3ntBzu2D/SuQekdrm3Zzjoi2Au/Y7NKDIveDAg8qHDOrGpQ6L3YZ1/ABOTG+I=
