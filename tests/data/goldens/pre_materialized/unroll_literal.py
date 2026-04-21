astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_hole(__astichi_root__Root__)

    @astichi_insert(__astichi_root__Root__, ref=Pipeline.Root)
    def __astichi_root__Root__():
        events = []
        astichi_hole(body)

        @astichi_insert(body, ref=Pipeline.Root.Loop)
        def __astichi_contrib__Root__body__0__Loop():
            astichi_import(events, outer_bind=True)
            astichi_hole(slot__iter_0)

            @astichi_insert(slot__iter_0, ref=Pipeline.Root.Loop.Step0[0])
            def __astichi_contrib__Pipeline__slot__iter_0__0__Step0():
                astichi_import(__astichi_assign__inst__Pipeline__ref__Root__name__events, bound=True)
                __astichi_assign__inst__Pipeline__ref__Root__name__events.append('first')
            astichi_hole(slot__iter_1)

            @astichi_insert(slot__iter_1, order=1, ref=Pipeline.Root.Loop.Step1[1])
            def __astichi_contrib__Pipeline__slot__iter_1__0__Step1():
                astichi_import(events, outer_bind=True)
                events.append('second')
            astichi_hole(slot__iter_2)

            @astichi_insert(slot__iter_2, order=2, ref=Pipeline.Root.Loop.Step2[2])
            def __astichi_contrib__Pipeline__slot__iter_2__0__Step2():
                events = astichi_pass(events, outer_bind=True)
                events.append('third')
        result = events
        astichi_keep(__astichi_assign__inst__Pipeline__ref__Root__name__events)
        astichi_export(__astichi_assign__inst__Pipeline__ref__Root__name__events)
        __astichi_assign__inst__Pipeline__ref__Root__name__events = events
# astichi-provenance: eNrlWUtv3FQUdubhPGdCW2UqGoogVG0i0TQPsYgEKqHAZopFm24ryzO+k2vPxNfyIw+pSAiJ0sXdYZasYMkC1AVrVixY8QtYsWfDDhXOta/Hz/E8mjSVGGky8rnH5577ne981775vPqNuiz4H1pWbMej4idEdXvI+9qTpMfefe8zb5VWWkQ98R56q1iglY+OTYuNfskHq4dKz0UeG7qj9Hr+jdJX4Z0d12j7Y5JykAxa0lSPLsCcWhtrMiYwJy23nWPf+y5RVPBeY64tKvY0AxnEa5boHDJUOXbZJj2ZdDo2crymQOtsNG6ad1u0olj7NmSPl/qT41fpFVkO57YIcWT5U81ELLAse3gZXw2mxm80S/hN+K40BfwWC6fQmS46OSKW6sfMjPsWdsWsgUWg8x8DDI5GjA9RB5a1KgUfJ0TJYODgNXwNfGchXfcAGY6d4zlvEpsYvZNwSdceQsUOFQuuPYnOdY9ig3S+eySrqKO4Pce/rnaPAr+ZmBXyE1llZ8OC4hpejCqILyVgw1eKsGHpJFFupFG+7/8tRhi/PSKwt1Lw4G38ADB8J23eCZDC70r4Pfi5Dd9dCX8QLV6g4q5ta/tGkr3TDuCFnCx5RHToFwiWIdDqnkMs1GdrKk+RLajmc1qD/kq0FQpKkAJjpTkbrZEuOCcmAk4fMEp4Ug4KE1WuzIOUIchCTuWwCO6PuWONO16IihO//6LbyrFki0OvR2xoE8OxtFZICCYwsrwhy3cJMb2JajgaDLQeZqAdmMRysuCH0NbzUDHA/XvuuMgdl0JUBDrNpSFR5jJrOjpHXAdZckszVM/nw8wdYtiOYiQ4gWtPaKXLfMJKr/BZrvc74HJkUVI538i0yY1JCVKBIBUIUoEgr+S19oLdY5XT2Ko2GIy/8Lsu8LuWIrbEgzXcVo4lhy3bOWyJRDo+u8+cPQeZG2dJHfzdWFyhO1H+ii8ukC5UPL4IC3XCDmBbgCxHuvLHIJb9EM3xI622iBsQ6mm0hicp8Wy4rawlTZ1GhjqNQurARrXrsKIArROqCZ4J1P4cqDuivzlDENjDFNNEbCHL+J+UV41j+zTWJLTa0SxQU/yzxL3r3HspX6IaGYkCC6J1FbWJpYB+wzMFxIP7RpIOw0Zp6QjIvNIndEY6fi1yzyltGcgRKMXsntuy25ZmOmmg/x75KrGQmZCBySVMQU5TnCECLOEZrTBuDnUKNLvYqcrbs8CLVu2e1kZenMowlo1WNFMOslkTnbaQ41qGDSr7SKLz/hZrwlPUAX+mS6vT2SvoJkCjN6cE4bxEdLMvopsvkYiyDVfXAliGqiH+ydfB2F4a6MOZb6ODW81/YBiofvgZ/hfW90WwvqGiJ9qgVkwkM6rXyFe9yxnVAwvSRZivUOn0OstoHHXT7w25w09vNbV5wZMSslKbF3RzdrqsJR5IX2aT1/Sr8HMK8qjfTK8lI2f6xnCX7aEugShuFoqivsPCpPF5LkVEOdXRbzPsQAz19wNynIcGbjEN/O0cNXCrr4Fbk2kgiuGi5b07mEXviAWPHv1zEhMeJQe/MC4NktC/IgltcN/XxpXQNX7jzb46vh5ZlFQm6+D0KP22un6WKjpbGk1Fqw7WLPV5Hx3PRER/H19E9W997UsoROl/pqBbYypo6XwUdCLOlH3OBblcHHROM9A92+C80i9BKYN+mupjnEk9a8rBOH3qVKTAVLSQ7fb8FxozsUUJvEpciAu0p8I1jnkvhhoXD7E48lYZiXoXIdMb62A19VY98QnquIdm6Djv0OzF5IqimFreFObgKQpLOnTmiRp3KCoPhqMyvHFPoVXTfZjJJGvK6cMXAtnaZJCNB9JpIcBP7rV9g4Ds+P9pWf8PFYbiQA==
