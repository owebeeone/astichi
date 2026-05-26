astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():

    class SingleBase(astichi_insert(single_base, BaseRoot)):
        pass

    class MultiBase(*astichi_insert(multi_bases, BaseA), *astichi_insert(multi_bases, BaseB)):
        pass

    class WithMeta(BaseRoot, metaclass=astichi_insert(meta, Meta)):
        pass

    class WithKeywords(BaseRoot, **astichi_insert(class_keywords, {metaclass: Meta, flag: True})):
        pass
# astichi-provenance: eNq1Vk1vEzEQTZvPJiVpQRRQqQQUokClcuLEiRYQUkiEihAntHJ2nXiVjR3tOm1zQOJC4eAb5u9wAImfwO9hvOtN49QJAYk9JFp75s143lvPfMh//VnJxI/IoohLUWgxbxRg+UW222fySL6XDZHrMG8s38kGyYjcs9NhqHY/6s38MQpGWKqtQxQEsWP7U+rZHVE33mujgQm66ntSrENM3yW+QxjEFFmXn8bWLxnywPq+MhWbTmoVha7T9ZXlVo8Fnnp/6AYoihyCkbc/HMuoIwqBTzFlsrkqyi4LHNbtRpjLZkaUMfWcdDcrqup12qJEbpHbo47IobAXwXnJ1Um65IbYciZ5hIxxxzmKfyXZJjtxoso76pA7zVWy28yQu80suZdiIlHq4/EJC70Y2GozZzUjKs+hitxn9CnuQlUa7eThaZGpqi3ZI3WwXYPcRwNMeWSxrAxZxGgwTs9XfweEH6MQ3mVblPsnU5ui0j9xPNxFo4DH7/n+SWJXmlqF/AqJMEqHiggjQx2WPBLl1z7tBfgARcBdvgN/cfzauVTIFbPa1bTWPo1wyOdUeRNqtQq1eqBrVVe5GDiVKI7sqJhLghj+JZWzYtrivKLZWjlnC5P9Cb0zuCjegmopgb+CWqUCb4B9Fuxzs5KpethlIeIsBNXCx6lI4eMhdoZA2WCBkF5cIGCtBYT5cf1JKyGs+JqjMMTe9FdJLi3ghLy5WIICRN+A6IXFJAxUdCfhfTkQwz+vEn/yBwbyJgM2UGtk5V9UxQOD4/9cCXL2r6c/+P+nxxOB+hNdFrUui1O6JAGY0EmYjLltEV/prc9JC3MUa88siCWtMoDWALQMoNemvx3QrL5EjU6SVdeSWBtAgLgZyL/mTkXc1REfzVVxbhAfYSlv07Fld5zmL2fyZ8NMVm+Yq2iGsIomrGInrKxDVhYStq4Ia6b9ainSqgB8BYCrALw9Tdq3c8fv7b9mRsHuaNjHc5mpJkPApMMuhwPX8FPf5eaoAxiRvPDZ/rB3jhV9w5etrHcD1JvTci5rxy3NuurCMEVZIv+yA6xrgI3JWUqHjEYcUW7e55/hSD71ZFs7XteON1O9nXcQtbxjytBWtmRVOdSSe2NWgjUtwZpdgoZ3Gi5YOA3YlGHre/VZoe4tN5xdEKrIhjDIgFpNRufMAUvPcmjecFgMMR+FNILpaj3u8C4bqCEOaKPzujzWpn6PshAnw9j+b6/a8iE=
