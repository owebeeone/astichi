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
# astichi-provenance: eNqlVs9v40QUdpvYbX62XbaLYEUJP7YUVSpwQIhF2lVoi4QCFtpKXNDKcuxJxsTxRPa4bbRaiQtwmRvDv8SROwcQNyQO8C/wxh4ntjMuKURqE4/f++a9773vzXyj/7jR1ZIPq9kR5cz4nLixj/gP3DS/40/4c37E6kPizvlTfoQ1Vj+/noXi7bfypX5p+zHi4tWp7fuJo/l95jmKAyd5Z9rTIuim53LWhj09B3sWJrAnqzn0OrH+jNguWL8tTNmelVlFoWONPGH56pj4rnh+xyHTKQqoNbXDCQqtkBB6MpvzaMgM3wtQQPigyZoO8S0yGkWI8oHGmihwreXbrnjMWzzEPfxaPGR1OxxHkDjeX8SNX2L3rEVAYjfLepL85/g+fiWJWHhHQ/z6oInfGGj4Tfh+kGHabHuC5lckdBNgpU3FqsZanwCd1CPBGRoBPUdm+qEZ24EgGR/jQ7BtQOyxYCZSWLZmJCKBP8/yO3wKlb+0Q3jmJmtOrnIvWWtyZbloZMc+TZ71yVVqt51bhfgM0SGNrDFwB+8sOwG/UORwJ2NQli9PHutVFRdNZ3SeVrfE0Y7kCBKB3LdPSRBRG2BzHYc77C1Rr94zK2kiy3r+EH6KNoCfvWcjD8GugkLoufrEC1xuyl125S4fyhrik1uXzuhHkTcOivLYokAkoqstpnsUTSNBisb0C0pClKkB6KnsfSHTBTstGUYLwtCzuDtCXGeeQ4v6ho5MKmskWpaNKQC2JUBTCqJN5zO0qJlZ2kZardkD+OW8YC6SoNsSrQ1o7VxJC36G2q8j/faKRcpD3lkUSbX6Xkkl+H12uJS6QwIaesNM7YJry3rXsj4WsxEU90HZ+6NUV/iRiR/DVx/+Tk18dlup4C9W070ro78rO9+XNH2Zb/ZjEWJvFJKpuuObEYKc3J545PgrU+LuStxHKW5GY37Lx3JL9SqMnn48VrW7kba7UGjjIh5GTujNaMEEmCjkPl7NfV9uuS/7GrZkeuR7Dirlv3EtsxIehvRoyCDvYy+D9VdgmxJ2k8xErLW+6y7ll9h3ClsNNpYbdSXGzoKjPLJcRazrAvmhDcqGcsC5CxzfMC27WRN6QYRCqjhpVP18s3Aq/dKKa2xLnlOFUVETk5/VQjh/kmHS6FOhipiim+rI6kI064UNhy5AwgROhbVWpqVVkYM6NbYVIhqHQQSz69JkrWSczeDcm8qhp0LX2Oano9K9hiIoWjHHLRTYQx+5fLVnO4BaA9RObkjeZgQoJmUXIOsA2QXI3YqCMz05MLnae0963yvOyzzwiwt+VauKeXlUOS+TSJKBeZ7GdPuJ+T8G5oEs64HU4IVqYN4JCMVeMO5R0nNJE6Mwm4sHci4K9wepe0ZXHvlQIitXbfzTjSLHP6/2uor1cpG/7mxo2lquaci/LH1/xb8Bk79Xj98/1gvpT6afrzRatXlpNVWrMt6/hErx31V9iZgBNyM/Qql2O5L0vMV/IF11f1sZpcfrXfbVjP8bx2vfK+2q5TxxCgMkL3JwQgOB6fX95B8kbMtQ
