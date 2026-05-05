astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    astichi_comment('root {__file__}:{__line__} {field_name}')
    items = {}
    astichi_hole(body)

    @astichi_insert(body, ref=Root.Body)
    def __astichi_contrib__Root__body__0__Body():
        astichi_comment('body from {__file__}:{__line__}\nsecond line')
        items['x'] += 1
    if enabled:
        astichi_hole(empty)

        @astichi_insert(empty, ref=Root.Empty)
        def __astichi_contrib__Root__empty__0__Empty():
            astichi_comment('nothing to do\nhere')
# astichi-provenance: eNqVVt2O20QUTjZxNhsn2R91d4UE21CJZatWLUhIwIofLe1WWqVEqL1DVCPHnmSsOJ7IHnc3qirxAHOHeQauuEYCcYPEBVzzADwKZ+zjeHZj0yRSEvv4/H7nO2f8vfHjQaeSfGTNCkUsG19zJ/Jo/EN891n8Oj6R9SF35vGL+IRVZP38ahbkj4yXlhfRWD14ZHmeZjOKfDuRD6yp5mvDdWLZhjiuzVzCOMSRNVtcJapPueVkqnKXZFphYJORqzRvj7nnqPuHNp9OqS/I1AomNCAB5+LBbB6HQ9nwXJ/6PO63ZIv6DtFube4RPhqFVMT9iuyqp7rolL3N3omGsm4F4xDqZXtp0mxfHpBFNioUIc+S35gdsrcSJWUaDtlRv8Vuw7fXr7B3M4eWbE7o/JIHTuK1UCeRKol6kksr0nwCQAqX+4/pSIPXV6iyY3YHVLYg30ihEeYK5oyH3PfmWSl3XkBjX1oB3McD2Zpcag+lObkkDh1ZkSeSe2Nymeo1NSlmZCgeNBEYk3XwakcDazuDCpukoyR7ZS2k05mYpz28AcY2hoYaoNrmI+6HwgK3WbHMlO+rrvRekYQnhLw+hUvVeLjsvRq5FEIqxIBW9YnrO/EAQ+xgiE+xU+wuNmi5FWUNapyFoTv2c+g3BYBHxQ0GGa6g01BBUZHGc8GDxVAAKKW8VpO3wMTE+CbEN7KETTU4j11baOQAtiV9bCTTiaRT1k20biHT22I+o4s2DW7EQK3/7zY70GfgIkm0jU7a4KStNS83MsCIo2YHNXev90B3srfoQZH0Prp9KI/zMbW5LwJ3mE2qApKQDwj5Su0yGJsP0eijdDjYxwP2CfydwvezAft8Db6zJ8sI3MI0byF9CSLwdMHYeyqj3ijg02LatkIKJTg9dRuzbwbodAedfpE6zcDS432J8YqlsC7OovFNzjZSzqr52noeDUM7cGf6gGnVfrtc7T7G2UdiQhxphJ5rU73i6hXWodQbqL6FaR2y7zKfZMlnC31u8JnKsHbmOPnwJPpmHqdfzaN00cH2AhLdLUqp7DqAdWDBUAL6cAQCpEV7rZtxy/VDGoiC5d9OmJku9r1S4r/ZKG1rRW7iuZE3qqYWs6wFcBgko791JhTNI0ELuyXriv4FmVYhaBWDVhbnHviCDZmOSIFJCl01NynLvlgsNwMqosAPYdOwgTST5TODM2mKK6pouCty40I/+ASFBmkFblLfGnrUiZdp2QF3NXDX0XbZCuOsFto/YN4F8zqYd8F8p6iZ0kjOrFjT30X9g+u7THd1uICuSJrvspPSXZZETZbZeRp/rW22/jI7wrYc4cxcLC2zPZ8L5vrjnuA9h7cYDbKddYQ7S9m+l9pmoOhuj9FtodRiPxVPJPt5maXdBFAFbA7q9RH8dyWjNMtf0OpX9hvg9XvBOvxjpdlif0rjPCPLSnNVmFKJ+C81T+zvMqpR2YDXDS+k6ZR1MJ6usQ7CRW+v1xE+Xu21uADhtXEt8Vwi1oEqeJuj+EIERyMAppZSNHzwH9wRU1g=
