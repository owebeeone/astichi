astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_keep(shared)
    result = []
    astichi_hole(cells)

    @astichi_insert(cells, ref=Pipeline.Root.Cell)
    def __astichi_contrib__Root__cells__0__Cell():
        astichi_keep(shared)
        shared = 10
        astichi_export(shared)
    astichi_hole(consumers)

    @astichi_insert(consumers, ref=Pipeline.Root.Consumer)
    def __astichi_contrib__Pipeline__consumers__0__Consumer():
        astichi_keep(shared)
        astichi_pass(result, outer_bind=True).append(shared + 5)
    final = tuple(result)
# astichi-provenance: eNq1VkFv3EQUdrLrzSabXVBhU4FIySGoBRFaUVGicgppObCwRamEuFSW157NuOvMWPa4SQ5IHDnMibpHTpw4I4EqLkhwgiMXfk3FG3vWM/ZOna0EkVbxvHnvzZv3vve9+cZ+8mvfyv94y01YxjufUz8NUfY4e/so+zq7xtsT6p9nD7Jr2OLtu2dRrLbsR26YokxsHLphqNlMU+Ll8rF7ovlaDfyMb8I5gYcDB1M4h7c8dparfkZdf6464Z0wIIjQbLTKNxDxHW3p0dCh02mCWDay+EDs6qJeOuFtNz5OIGh8qTgZD/nrjjM/OKaUOc4XQYSEV8fJ8GX8WnEufmO0irfhd2Vk4TeFL5d3Z+j8lMZ+7nBhP5eIlZAWEov3PoEEsICSO2iqpYWIbOBdvAMq6xBieoIIS5RCL6IJJeH5PPqdB1CQR24M62zMN2an2ibvzU4dH03dNGT52p6dFnpdTQrR2KJ2XZmHHu7Lr5e13JQlmSEUNWZDhKQZdhLsxshvTiC+unTeOgdJEhwTlZE1BndCrFbLTowSuKA41uL2fUbjEmR1vx0RQC/HVwD4VrVARYJqkV8ZrauA+CY7jxCA60TUKRsbQm7MK96qeG9J2xbYbi6k0vZQGCYinodSty91L6kc6i5eSScGyTvS4R6/qgDvUcLiYOI4Rzny85Mc54bjHMIXwAxfl1bvF6DDH4zxLfi3D7/bY/zRkjjCd5aHDv70v8HMPenwaMH5V8146B5SkjCXKEzg3miDt2cB8ctSa2DA3gvXnw/mBUBnEY1Z9lw4DIzp+V5qvSS1hmYgbC0AASSID3zk0diF5gDyBOiDXWOMAUnQYozb0nGBrmqMtEm3iNTia5I9Veu1BE3xVgzUmFdi/YAJdKYMaaXAT8svFWt3ztnVKFfg5BV5spWzPzjMeFugvVET/w6TK2+BqlKRyRWpZLjaooivxYilMUkAO96Y93LmiIC6T+TYqDfqizBHW9q2jcyxDu2dwCiJc/b4W+r3pf6WAo3u5nI6MUgUe9w0sIeamOWJBYvI1f/GJHqy9y9gkpquapiqi2pB9p9TkKfLjc3ITZJsea7HX4LusxrLly3zk1T7mW9Q6InYmQhGghC+mwfzLX4yltY70nq3vNJQSdxaIG/liO+4UYRIPrOf1RTelZHCUP04IPcibVyGaMrqSZ+b70nzm9B7qzQS9q0DX3vM2XFwjMG8vMHIVle4Ja0/LK+wpyQmvjOWD+EfzASHf6y10rZEfYH4amH+adKtlQf/UmEpA1/h35rJB/9xATl1VWc1E9RCpAbRn4KY8F9GJjBOUW5PA+Lm5KhmqS0tbbC0i1lqag2bpVFYo2lh2pWmfVNPPLy7YllScSAVX1UY0O2H84GsxzNcHgbNb5Pdi98mVRgsW3KDM4NIr1TtwYHkmxQeyfDoLV747/0L4ZFwdQ==
