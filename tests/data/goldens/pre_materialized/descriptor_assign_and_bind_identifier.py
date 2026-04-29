astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_keep(shared)
    result = []
    astichi_hole(cells)

    @astichi_insert(cells, ref=Pipeline.Root.DirectCell)
    def __astichi_contrib__Root__cells__0__DirectCell():
        astichi_keep(shared)
        shared = 10
        astichi_export(shared)

    @astichi_insert(cells, ref=Pipeline.Root.AliasCell)
    def __astichi_contrib__Root__cells__1__AliasCell():
        total = 20
        astichi_export(total)
        astichi_keep(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total)
        astichi_export(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total)
        __astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total = total
    astichi_hole(consumers)

    @astichi_insert(consumers, ref=Pipeline.Root.DirectConsumer)
    def __astichi_contrib__Pipeline__consumers__0__DirectConsumer():
        astichi_keep(shared)
        astichi_pass(result, outer_bind=True).append(('bind', shared + 5))

    @astichi_insert(consumers, ref=Pipeline.Root.AssignedConsumer)
    def __astichi_contrib__Pipeline__consumers__1__AssignedConsumer():
        astichi_import(__astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total, bound=True)
        astichi_pass(result, outer_bind=True).append(('assign', __astichi_assign__inst__Pipeline__ref__Root__ref__AliasCell__name__total + 7))
    final = tuple(result)
# astichi-provenance: eNrdWMtv3EQY3+yuN5vdZCmlmwhESw5BFNSUhyBqKY9uEhBiYYsCQlyqkXc9m7HX8Vh+NAlSpQoJicOcwL3BiRNnJKA3JDiB+if0zr/QGzP2rGdszz4CKQcirWKPv5e/7/f95hvf0e7urpXiP1LR/SAitQ+xEdow+iZ6fi+6HV0k1T42jqOb0UVUItV3jlxPPNJu6XYII/ZgR7dtSWcYOoN4vacfSLbKphGRZerHHCATIEz9kMogOIpFP8C6MRbtk5ptOtDBUbdMGtAxgHQ7wDbAw6EPg6hbIi32VF5qhn1S1b19nwaNziaeUZs8BcDYsYdxAMBHpguZVQAitIaeTPyip7tldJ7+LnRL6BlmSyf1ETw+xJ4RGyw8j1fYHVtNVkqk+S5NQGBiZxcOpbQ4LBtoA61TkSUaYngAncAXAk0X+9ixj8fRr9+kBbmle/Q+6pHG6FB6SJqjQ2DAoR7aQXyvjQ4Tubq0SqPRWO3qPA9NtMKvzki5SUsygtCdmg0WkqRY85HuQWN6AtFzc+et1vF9c98RGVkM6DvBIFfLmgd9+oLMbYloHwfYS0GWt1tjATRjfJkU36IWMElQLvIL3SUREFkOjl1IwXXA6hT1FCFPzStazVivcN0K1V0upFIbQNv2WTwWl13hsmdFDmUTT4R9xcoL3OAm2RSAH2An8Mw+AHsx8mNPALwEwK7pwUGwQ+8p2NCLXPeVBHrotR7aov+u0N/rPXRtTjSh3fkBhN4/HeTc4Ab3CsY/m46K+g52/EB3BDJQs9sg1ZHpGGnBJUigwYlRQFrjMsAjF3tBNBEULWV6vuNSj3GpthoOqwU40BVIWgYcYE+nLUIplDYA1Zsao+n4sBjjeW44wVg2RjxNNom0RBY5h4oGrDCyIhWPEmRciaVOwDAaBlAqBbqXXolY62Pmzka5QD0vcM+leA+gBiNSZZifKol+Iw25EbKiST4XuKjiBYtLZNGDQeg5PkXQoEeaMYu4lMYP+BYyuWkvzWralwHo2Kbun7hnlS1CtAAHevzO6kbRkkb5Ou2Nc+juuAPqXKahaovGTHL89gR98IDK/pXrg3PqPmgX+qA9M5TJjNUo8PR7okJ6vFkB1jOZeYJiely1+DItGABsAgAgTfpEpyrqaxSo76RJnvpm6OHpBKTm4oc5iOWMN3PFnhxzwSFE36tJDf1wuiz2Ixf+Cf2cYSYFR6FfpxMO+n0GIS1JTf6v+Qj9wXgI/anknpNMMFWuW1VOMEuUsXw60npsirGuLpRKXGWFq6wKGMmW1sK+YkVw4lUFJ4pmS53KAw1fe2RDjZzh7RlDTU5WcFbWRLYy2xMqc2++Od6l1BTNP3yiT2nBjKRg8uRZhD5pYLpDe6DP5iN5Y/gq2ReY9jrX3kjfqi1W9Fwsz8Zwr+muC5nFTBhjmUs8XjrrfxK60uEUAVa4NAZ6Vo3DSiO5zA28Gh8utG3TueFKRwAbDoNc3WT3W1z7DTpMlLHL/Fc6hnRG1TxzH1ELYnfUhO+3ufb1NAtbYgVmPW3yJx31lqaEx7y0V417KsHZWr7w1lssiCni/z3ztfItPJ3+CvEqlmT6m0wz1+alGTaCxTs/NE6faKRJ/KB4WpC3vpZqA7d+SVBV5oNSWR6URBdrfRwWGji717bDfnFFz8XQLmzI7X9CXNYgD8PZdHV/HrqybCZ1WjRl4ThM2XWOoiyPPlJzUy2ZFhXstBX2rc9TPes2s54tquTwCld6kyrdocvWF2PNvvUlExNktChcXRcEk7PTScjofpGMttVktFMgo53/LxmdKTb6o6WjCae0oenkT2ka19TEKU1FJ1oQ75iZsDV+eGOqK8rmerwcw4EJtrigdNyS9dvjw58cT3t+REz/PLQx+/NQFg7zll5hTLEkVyr3zQfyj4MUHdiDyafWy38D3YVf2Q==
