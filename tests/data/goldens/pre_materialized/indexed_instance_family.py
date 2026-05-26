astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    result = []
    astichi_hole(body)

    @astichi_insert(body, ref=('Root', 'Step[0]'))
    def __astichi_contrib__Root__body__0__Step_0_():
        astichi_pass(result, outer_bind=True).append('step-0')

    @astichi_insert(body, order=1, ref=('Root', 'Step[1]'))
    def __astichi_contrib__Root__body__1__Step_1_():
        astichi_pass(result, outer_bind=True).append('step-1')
        astichi_hole(extra)

        @astichi_insert(extra, ref=('Root', 'Step[1]', 'Helper'))
        def __astichi_contrib__Step_1___extra__0__Helper():
            astichi_pass(result, outer_bind=True).append('step-1-extra')

    @astichi_insert(body, order=2, ref=('Root', 'Step[2]'))
    def __astichi_contrib__Root__body__2__Step_2_():
        astichi_pass(result, outer_bind=True).append('step-2')
    final = tuple(result)
# astichi-provenance: eNrtWM1vG0UUd+OPfDgOatwU8SUV2kau2oQ4UsuhFShKQZVcVqLhVkWjtXec2Xi9s9odN/EBiQulEnNAYjhxAHEArhz5BxDH3uDP4c161t61Zxc3dmkPtZRYO/ve2ze/9/u9N94vi9+/fjEXfnjeDJjgpU+p1XOw+E4YxmPxQHwharzQpFZfHIoayfHCx6eeL+9+pW4WH5lODwt5a990nNDR+DrybPfcVnjPMLvJoAu2JfgqPNNuERsRCs/k+RY7Da3vU9MC62vSlJ9HkVXgt1DblpaXj6hjyev3bdfCp9hCthsw021h1Da7ttPf9voiaPKSY7vYpaKxwFda1EG03Q4wE40cX8GuhUZ31+Rl3KJMLpF3e01eMP2jADZPNoa5kzf4RTRMyqeUIfQg/C/IW+SdMGvpHTTJe40FcrmRI1fg+2oU0+RLHdw/ob4VBtbapKzmePkTgJTZ1L2L2wBRzRh8WIS4K4Em18km2C5D7r0udlmgsSx7NKCu04/2t3kI1X9k+nAtDL7SOYnd5OXOCbJw2+w5LLwudk4GdkuxVcivNGBJaS8I7CM3SYZFBi6YTYJZ8nEAISR4OV48YNTHUfG1MJYUjKQScsUG3iboigfp6GuxnESUr7K+h6HyXYmTMFJwX474Ds98bbQnUk3shLw5+cy8ipaHaKsq2uYYAqSk96sov/PRhrdDusRDrg/polutjxWd3OTXRsxtUZf5djMir1Q5QjsIHTDswTdQgnwwHuD2gCnkQ4N8BF978LdvkLtR8TOAAjruMfm8HsMJYmRCOmoRnhkE/6GvVHw/0/tVlF81jm+OLyp1JliVl3znKxSy91ETuo4I6be0T8PGk6AgqTzhhY60ifh0ST3pSkLdG8lVc2w7V4ctCHADcZqeh+VzMzG4EcPg51hGvBRAWbd2BPklSmpLudxM0ise7Za2G92K+tiahVvUN0Gx0EpBhuCfUcq1qJTQq7HPRLZY1p9RLGN+g938MHL8ked9aJlh1Yqf97zkkCMPZedKAFaQslBw6RJLGC9K0TzcOUy3x9Ntd2x1wArd/viij1nPdwMgGTJ4OexjHvTvrpoqc2oIddUQ6mdqCLWMjvB4yh5Avv0fZB9nCvkJ8omX98lINLMomfxKfptJvfU5qvc5zzRexKfMN0X2ZFtPn2xVrSCq6US+oSGyYi5CYTLhdLuHHQ/7cx5ur6g8PZVXB1TeUvyYIPTtdELf0RL6TuTwe+b8IX9kM7magv3x2+dyualcNfD/CfD/lTFlyNPJgVFNHzB13YDR2pcinqeZ4+nQGFudnEfDvf8t5xD5J03IeMbyzOM8UEseCIpwyJMQJRXSOJc+8/WrM1dcd6Q49iTt5n2awGnopFVvhpPDruq/u+hVt33BB4fdeR77XzohH38jpTKm4oWXQsWqb+8+hx8GZ5byvVjp7k8c29q2azry2HaQzKmgIhUgUnH0Bibj916Rhb+yJrcnQy2pUJVn0KD0W1N+F5LsjYfcUCGRMZb2xtknke6l0ETK16d7/ac/JSQiPZ0ug5T4KctxXmgMsHoXZh+51MeDF3rb/wLZelEA
