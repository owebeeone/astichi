astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    def func_combined(head, *args, **kwds):
        return (head, args, kwds)

    def func_plain(*args, **kwds):
        return (args, kwds)

    def func_star(*args):
        return args

    def func_kw(**kwds):
        return kwds

    def func_one(head, *args, **kwds):
        return (head, args, kwds)
    source_plain_scoped = 100
    seed_star_scoped = 200
    source_kw_scoped = 300
    head_supply = 1
    seed_star = 2
    result_combined = func_combined(astichi_insert(head, astichi_funcargs('head_slot')), *astichi_insert(varargs, astichi_funcargs(2)), fixed=1, **astichi_insert(kwargs, astichi_funcargs(**{'seed': {'seed': 101}})), **astichi_insert(kwargs, astichi_funcargs(name='x')), **astichi_insert(kwargs, astichi_funcargs(flag=True)))
    result_plain = func_plain(astichi_insert(plain_args, astichi_funcargs(20)), fixed=2)
    result_star = func_star(*astichi_insert(star_only, astichi_funcargs(7)))
    result_kw = func_kw(fixed=4, **astichi_insert(kw_only, astichi_funcargs(msg='solo')))
    result_plain_scoped = func_plain(astichi_insert(plain_args_scoped, astichi_funcargs(((out := source_plain_scoped), (__astichi_assign__inst__PlainScoped__name__out := out))[0], _=astichi_import(source_plain_scoped), _=astichi_export(out))), fixed=2)
    result_star_scoped = func_star(*astichi_insert(star_only_scoped, astichi_funcargs(((out := astichi_pass(seed_star_scoped, bound=True)), (__astichi_assign__inst__StarScoped__name__out := out))[0], _=astichi_export(out))))
    result_kw_scoped = func_kw(fixed=4, **astichi_insert(kw_only_scoped, astichi_funcargs(msg=((out := source_kw_scoped), (__astichi_assign__inst__KwScoped__name__out := out))[0], _=astichi_import(source_kw_scoped), _=astichi_export(out))))
    result_multi_scope = func_one(astichi_insert(head_ms, astichi_funcargs(((out := head_supply), (__astichi_assign__inst__HeadMulti__name__out := out))[0], _=astichi_import(head_supply), _=astichi_export(out))), *astichi_insert(varargs_ms, astichi_funcargs((out := astichi_pass(seed_star, bound=True)), _=astichi_export(out))), fixed=1, **astichi_insert(kwargs_ms, astichi_funcargs(**{'seed': {'seed': 101}})), **astichi_insert(kwargs_ms, astichi_funcargs(name='x')), **astichi_insert(kwargs_ms, astichi_funcargs(flag=True)))
    out_multi_scope = astichi_pass(__astichi_assign__inst__HeadMulti__name__out, bound=True)
    out_kw_scoped = astichi_pass(__astichi_assign__inst__KwScoped__name__out, bound=True)
    out_star_scoped = astichi_pass(__astichi_assign__inst__StarScoped__name__out, bound=True)
    out_plain_scoped = astichi_pass(__astichi_assign__inst__PlainScoped__name__out, bound=True)
# astichi-provenance: eNrlW81vG8cVl8glJYrUhyVKFkWJsijJlqwPx4ldNK0bJ1ZauFHNFpZroIeAWIkrL1cUlyG5kYW6QHtIncPeyvZSBD20Rf+DXoOcWrS+9Nge+mcULdBD38y82Z2dXS6X+jBSRIANcPjemze/9+Y3bz7408Qvf3VvgP7ZcbXV7tjJR2bFqmmdX3RKpZ93Hnd+0lmzlX2zctr5sLOmD9jKt583muTbT/DLxMdqzdI65KsdtVajiqWXXPPQqh/Q70rqsddorFrp2Bnos3qgV8u6CX3a8YP2cyr9PVOtgPQ6Ed23k7VqXaubnd2YPaLVK2X+MW6PHJi1snl42NLand0Be4x8KzYtWPu2ojaftcB7fdrpXM/ZM+Uy77tpmu1y+TH9v6Pn9QXWrX5tN6Yv7cb14u6AvkxMqfbwkXZ6YjYr1J7ve9pCPpFW1jJgp78DELSrZv197RCGtFZif22OUJ0Ao6/rKyCbAletY63ebgVIphtmy6zXTvlwVj6EaH2sNuFzp2SPHJ0IX9rpo5NyRTtUrVqbfk4cnTC5YaEV/EuSqN6SutLfskdJ4ADK433AugKd6XdlobeZDzrJHDDtiTttsRVdgzDaI2q9brZVggE4kGmfNjRimYyzU0LMJgGzGGA2Ayjr9/Tvu7b0Pej8hyX9KRfNoSiB91vQ/334955Xw1aOTiBGHrUlVFsFtQd87OB88rHWtpp1IaX1UWhOPLEa8jTQGGxrnkzSn3hShqRDBhNgAjrxiK6A6EcoNIlCM7JQWRCaRaF5a18TmtNChrEWxW1R7bGKdmA21bbZhKkCkxriP9Sko2x1CCJ2msagAblz7GSyN28DUmKEpkSjplbrofnQPXoJ6GQCOklAJ9nu0QMERI1Z1Jj3BO5AiJbuwlfzhWfFE54khicZFB6C/K9RaBKFZhjyvDmNzVctbk1xW1T9FDz7MfX9BYU1gbBylQBYUxTWVlttnhHVYehjHPoYhj6mRFRLXeAKgSeFQ0yBrXGLtyhui3+IwzhErhIwxCE6xKOT8AGWIuRDGjobg87S0Nlk13zwBdUdYAYHmHEGmMEBZroNMI0DzHQf4DAdoFnXQkfoHdQTZ1Bj0MEodDAGHVwJ5z8imkXR2UgziGjMo8a1s80gL8GN4wwa70Zw/0KhSRQKJDguNItCSHC8OY3NjODGMUTY4g/RGIZo3Fl1k++1WtVnde+qNAST7JnW9hcDUy3Tah5ojNzKrQOzQda8PFkG9oBFNacUgb6uYF9X2HRT6WoxvGPWYQrDgiYsGProbgVWomq9Qpc5ojiDijlw8mlJsgaNxuDgwIDrsZGAj7KzEy1Nq1DCcD01MiDouDiJRidZiMBFY4LadR37s5ElLSg8hcIz3C3RwkxUtxiGUHh0cWsKjU51devR5qDj1xT6NSX6JZqI6FeaFCHlltVo1E59LmXRXhbspYORcj3KIvlkkQieliQL49E8SjkB9PkzjdamwVoq2J+Y4880zkQiPMr9ES2MRvNnvKm1oCIUqj3Jq6to8yqnyFF9XKCbKe/0fuihi6vIBER3EZxcIfTSXdse41V5td7Smm1vPU7YYpaSAcuJlR5cJcuH9DvB+yVUTqtoaSfAIIgh60HPcmTsFMu0mtnuODEieldQb55At+kpt7CO1bB5FoluFv0dsIf2IE2aWsXLKyEDMfahZ4/rpF7OIQhzQaDZQ2wXIQ1Z1gvp8yO5zwhwCYksgjQZDNKUC1IOQcqhX3njR6R7kmpLsNQVKWkNojzZsg7hps2D4Z6dOKw+J8keNuXnwNwImJ1j/IAtitti/Maju1fqMzh5MJUPDU6S7tyk2Mhq54wNQSpoJLATf7960PbuggBNsoL60l8htObN/Cx2M0d2JUl6UEBV/ySqGn+lnMTsfSKZw012jC4Gy7tfB0PG34Lkd7UA0W5NbGWJsSYpAQUhjtLbbvLlMfx5BN6XdZeeEMYfe6lcQjLob/mniT343BvtGbST82Ga82M695XH1FYOa+qzAP75NBDVOR+qc35U832gqgmr8zxrYiUEX+6xMUoJkcESAk8HpPphAQ0ugMFMz/rhZx4wF3B3u4CJRcDsJ/YLVLdI+frNQIIdYVW/n2Rl1YteALOBC+BU8AKYdSPLfGKQvInScnIZvyUehVWPxMo30Mo3LQ71HbdFldC/x/NDDOe9iEU45kdg0VtAewWnCA9Lj997cC5gTV7AAxaC8wvvmPtKlwK1VaQV2BuB6ZKiOy9y1toJ1bzobBk6Y7lUwF12Af3KG8cxWi5xh8nJwG3XjIjobR5yMUS3I+5yMOTk2EcK+CJaW3R2OWEB/9wD1SJuehbxtAvJdS3qBFAcGBdxGi0y3sSWrNty3mVnkZoq0nlyJ7jwhs2yP5NkvctYe+LHraClB6ous2Z6l/Vpd22Rki/vX4Dm3cRjQ2Bo3rHEgZGTtLtsARLDeZdnm5gfd6Nl25S4AHU7gFhCu0vu0U3kdWgJl+IlPEfrdx1aorpFqv9uYDJccdch4Qiqu4XzpsWAndqz9lsHzWqj7TknCzgPBFlygVfhl3/ObiDJjtSkaMRNq+1Dn1xTJPCKYRh88J7TGiPUZ+PfjJzkaxSvOrQYibi4h0jBJ68P2+4Fn0rPAsvkSKFdLv+AwLxHAS6Xye1buRzs7hL2yTyQ3B2NSxDL8r4WLUzcTrRq1QPNt6sZCLAsXzcJqKiBXGgPljuhuS6cuhw3THrqwgOhQAdJ6EDBO5sVaeZJcVOQMBRe9TMuEK2wYlTB8hRbfPS9RfCN5rP2XPI5gb0luvnMgieKT6P4rOuzaIVtaRLoM7ZowsRKCmcOyBZLyBbvnrlEI1YeopXvWpyFHrgtqkRMH3AGFZnug2gMOimUaN0ItIhmi7zy6KNSKyLKRLdwAZVakdoq0kXinUBCnXAqtUA+lQ2ct2D7b0zE2E+ivRiLZ2UP0gyZEc5rigYwHgnei7iPTGeD5sM8m8OCeE64Tw4sIBL7plV3T88cxvpUIKwMhtrXokpOFXwMX4jA8FvdGJ6cmfZH8IU+Cb5gBbRoYeLGMtjrxe6FEHYvdKORnkxp7MTF8PZk9FGfOGf02WBGz/kYXTrwSXjZkc06RgXv0C2JyvriU5JcXtx3+xKp4z6nOJGL7ke8onK2JN0IbhmNLjtXVNF3Jst4rLjsnjKdcWeyjKsHsVS0uO2823LenckyNVXcXQFzDwK5cwx3JoHMKatfwAbFj9JfYhSlS2PVFM6rjH/qrzM6/I9LhxMonLVk9WwEotroRlS7J9FpKoXdR6WplOCup0ULE+9JU9ysTFMpH0L8SdL0Wao7405cjEFPzvKG7PVVoZxbseOolacgfsGVJ5uXjCkeWOJsJTcgO0xXpKodTqgi9+30VzMew39VRhW+/F1Fs6uRasa/exJrFfFZxXcdPS6P/UR3HZSv4zF+LvgIhl7aHktHv7Le/0lt6FH5GpsSNeWCNtSb3VjsISD4iGbAl2Y7HanaOtNeOjp1IfA9qcsbp9dPXdhxVOoSxC+Yuq6j5HV8C3We3eENsHMDJ/BC8LUPPnrwzX1Z9bxz/7K3fUaHGXilRNvs7QzK4r02e8ZncbdivYSd3jn3Na+UvvY1r5TL2tfcQMkbmDl54wnraxUab+K+xnmZEnVf4L5GWcPXKGvOa5Q17HHtYl6jrIOp9dBZk2KvUXyTRta8nAcpIQ9Hoj9E4e9HIjxCMf7BXhZ9qZ6grGPM1533sVJ6XXoWGGOJHiqv6QmKMQh11YW8QfmKgmosxYI452JeoPTEVBNK/JviCxS+Z7gZ/QXKOBSdofuQDbS5EeURK66pAqAb+FJmwz2+9mq8VOjq8jJBGWMDj7iI+Hbfy+oG1WQvdW5Z+/4WVfLoFkdOHOWtaMiNEuS6H4ltosVN9qC4X9w28fRkE3/B48NtluH2O4bbJl4aE/GbfeO2STVJh8u7G9a+v0WVPNrguImj3Ogj48JuS7bQ5tbZMm4L47vVLeP+wOqZLxhyW5hxW2fKuC2qKWac1KJKHjkZJ44yYsZNEORCb+q30eh2lHNYP3TbuLxuu4/OvRo5Bt0/GXRE/BqKv9E3dNtUky3vt619f4sqeeS8qhFHeZvQ4Wmfjwrk35/K49TXQ3/OGvwypKkddqTtua2QX8d6K75BMDaIxgasQPMBTeKvdqTfHGr409Dqs7rZ1NjvU7f/B4xog7k=
