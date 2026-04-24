astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    source_a = 10
    source_b = 20
    astichi_hole(body)

    @astichi_insert(body, ref=Root.A)
    def __astichi_contrib__Root__body__0__A():
        astichi_import(source_a, bound=True)
        out = source_a
        astichi_export(out)
        astichi_keep(__astichi_assign__inst__A__name__out)
        astichi_export(__astichi_assign__inst__A__name__out)
        __astichi_assign__inst__A__name__out = out

    @astichi_insert(body, order=1, ref=Root.B)
    def __astichi_contrib__Root__body__1__B():
        astichi_import(source_b, bound=True)
        out = source_b
        astichi_export(out)
        astichi_keep(__astichi_assign__inst__B__name__out)
        astichi_export(__astichi_assign__inst__B__name__out)
        __astichi_assign__inst__B__name__out = out
    out_a = astichi_pass(__astichi_assign__inst__A__name__out, bound=True)
    out_b = astichi_pass(__astichi_assign__inst__B__name__out, bound=True)
    result = (out_a, out_b)
# astichi-provenance: eNrNWM1vG0UUX8fetWPngyZuohJKIzVSDRKfEgjBASWFqpKLqQrqrRqt7XFn/bFj7UcTHxCVQIjD3FgOcOLEiX+EE/eKCxIH+B848GZ31js7u944yEGN5CSe+b03b977vd/s7FP9+5s7WvjDyqbrBcz4hPb9MQ6+C155EHwRtFilS/uz4FHQIhqrfHw2dZIp/Yk59nHAJ26b47FkM/DtXjjeMSeSrzWrH7ANWMfqEQsRCuuwcs87C6H3qNmPoV1mjC0b2zRor7E6tvtI+tqjY0QHAxd7QVtjW3xWHtr0u6xiOo9dCJrsRCuTq2wPoXhhh1IPoQfh74Dsk2vRmuSl9hq5Dp+X2xq5wf2YrDbCs1Pq9ENnmflwhH/jo9GIxhp3YPOeRe2P8EBKic0zQY7IIUDWITx/gm3PTQCNKXWpPZ7FkR8+gmI8MR34HnRYfXQqTbLG6BT18cD0x174XR+dRriaNArR6FHdjGPXtR7byWJVD+DYU1JUc6nv9DAyeVI0pn/mUWdePXWzNUgPaQCsdpvarmfa3tw9abTrrDKy7H7QEVaNJEVsw5tNMZRswjMwR8hJ/FD4OckNr8vDuzsPqiyMy0lQ9+ZxNMmnHYFpCAxf4H5HMeSDtdiKbIr/XkhWJ3spolSEbQVsN8D2UI6U6IA1BWpToK7w0G6FLJKNd/xuzsirwtVr7GZC2x61PcfqxszlfYnQmwgdA1nIG8Li7Yg65J0OeRf+vAef9zvkg4QNhbtkW/Fi1mRKHU/tjqRMW5lN3wHsTKC2BWo33rTGqqKTEhKWOWWZ3qU+EEWu2rdKpzX9bnbEVAJqZtqxuZBJZep7i0lUjkiU3tm1FNQQ0Hoel+rncSnJMj7LZlnmQjbLDLA/CtR2wpg8au1mqLV7bmRzcR5hPF2sjU01LnaU8NQMxQYhC2QB2IkQlz6ERM4XOoy3kFf5dFGLG/WH5aMmv6wmoFyWhc7vLnbeUKq6OObMgpht9XGPOiYINJyMcG7DwsXtbLs4S7Trgh2R6GQ1bCE2Ss1TAf6KlR0468LTYP3Y4yLle1g6DqSIKly80nGUwHdJ+NbCwxtcBKx0rMKiHJQiWF5Q2SFWdbDnO7YL58z9DmuER88UTtWJONH/u/K+hdDJ6pSXnF1Aah8C9p9FUjuvCvn6/xTVkMNLCurDFQuq0vPnKuhwv6Rplyai5OdV6ObJc6ybwxbP3+VJZ+z/ktST/Jovl+S3lepjSxJIHZ58sJN6ygEhy66RHUna+RlY/56VVPJHkZqSP1np5IJCivM29BcXUPJ3rmjmP2XpwNzoLpHUUReWOljqUR0LH0Om0BTp6LmHmvCQe6APp1Fzc+BVAXxxCXHUQyx3fqN94HezI6ay+kGsVfKmDorTodxdDGFpFKZjSNV2M0QYRkF3Dr+J8mCIPBhL5sEIsXIelBFTCWCeB3k3i/NgONiFG2o6EVVhWgVTI75Z6p/709SrCBxdbFvSXomaGu6pLjxtQxAJ9MsoLT9FaeG4KwK3xzmfmlkXM/vx3uQA95fXEPWFQZqtR4UvH5RCPbtA0+c4yxmSW1q5gmNxS4cDiUK9wrcJr/8LH/2pOw==
