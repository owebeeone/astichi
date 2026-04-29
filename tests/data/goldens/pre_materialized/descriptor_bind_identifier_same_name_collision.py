astichi_hole(__astichi_root__Pipeline__)

@astichi_insert(__astichi_root__Pipeline__, ref=Pipeline)
def __astichi_root__Pipeline__():
    astichi_keep(shared)
    astichi_keep(shared__astichi_scoped_1)
    result = []
    astichi_hole(cells)

    @astichi_insert(cells, ref=Pipeline.Root.CellA)
    def __astichi_contrib__Root__cells__0__CellA():
        astichi_keep(shared)
        shared = 10
        astichi_export(shared)

    @astichi_insert(cells, ref=Pipeline.Root.CellB)
    def __astichi_contrib__Root__cells__1__CellB():
        astichi_keep(shared__astichi_scoped_1)
        shared__astichi_scoped_1 = 20
        astichi_export(shared__astichi_scoped_1)
    astichi_hole(consumers)

    @astichi_insert(consumers, ref=Pipeline.Root.ConsumerA)
    def __astichi_contrib__Pipeline__consumers__0__ConsumerA():
        astichi_keep(shared)
        astichi_pass(result, outer_bind=True).append(('a', shared))

    @astichi_insert(consumers, ref=Pipeline.Root.ConsumerB)
    def __astichi_contrib__Pipeline__consumers__1__ConsumerB():
        astichi_keep(shared__astichi_scoped_1)
        astichi_pass(result, outer_bind=True).append(('b', shared__astichi_scoped_1))
    final = tuple(result)
# astichi-provenance: eNrtWM9v40QUdho7TZo2oGWzBcQuPRRREF3o8kOwPbVdOBCIVgvSbg/FOPGk48T1WP6xbQ4gjhzmhvkDkLjBYcWJMxJob0hwgj+Cv4E39iQzdlwn0ab0QqWo8cx7b768933vTfKV9u1RU4n/aNnwg4hWPiZmaKPom+iVe9EX0RZVO8QcRkfRFlao+v6Z64kt7aFhhyhiGweGbUs+vdDpxutt40SKtWSZEV2Fc6wutnRM4Bxa7gZnselHxDBHph1asS0HOSRqLdEV5Ji69Ngltk56PR8FUUuhDbYrL9XDDlUN79gH0PhKcjJu0ud1fXSwR0ig63ctF7Gouh7hdfxcci5+obWEr8PrRkvBL7JYBq0O0PCUeGYccGI/XmFPbDVZUWj9A0hAYBHnDupJaXFYNvAm3gCTGkAMT5AT+MKg7hKfOPZwhH7jCAry0PDgOWrTlcGptEnrg1PdRD0jtIP4WRucJnZVaRXQaKx2VZ6HOl7j756WcjMuyQAhtzAbDJLkWPGx4SGzOIH45RnzVggS35kD17MJLlFyv0tceN5ZEFKFVvZ83zp2RO2WA8g+CjKsq3jIh1KwYxWqfRIQbyyHbNwKA1CPlWCBEgVrUFLKDPIbrZoARFeDoYtABieMUVF77uReS0Uvc98y+K5OJFfrItv2GZ4ht13jtldEDuUQz4SdnJVXecBtuiXq1CVO4FkdXb8XazQ+Sdff0PUDeLcHisCvc7dbiT7w2238Dvx7F16323h3RsrPwyb84WJI8xkPaEwEPy4mRPWAOH5gOIIUuN5aoerAcsxxrSU2YG9uAtDGqALozCVeEJ3Lh0Zuen7kVk9xq2Y+E65NMAFWEG2YqEs8A9QBfR64D36FGC3HR5MYr/PACb3SGL8ssk2QKnSZN3qhvTLrqLTsQRePK1HbCxg9wwBJpcCPx+8E1upovKRRluDkEj9ZiQcVBIyoyuheaIn/oBrXQNoqSWWJW+V8tskluuyhIPQcH8jjtWk97h0ujJkTPuKeQKo7iVT3L0mqhxcp1cNpUv1urM6r+PvFCBP/MIcSAWBfLSnKk4gR/5SvPvzzYuX2Czf+Ff+WklCOmPDvxcrAf86inP0FKAf/xRSD/85VyTwTVuW+au6ErYG2fLgcemzK9reTiqp80KpJoUYVlSOth52cFaHet3LUK67B40OTgcufLm7oysndnTJ0M7aCzukQ6aLsnlOUx7Ndhl3D96PZ70UYQa0eCPWtCWpkGE9XCEwQT++w+S23ja+TrsG8N7j35vhTNcWKkcHyUszyiuG6iEVMwRjZvMbxwjX009CVvuFhhxVujIGWjEjAuMm9d8A7VRv5iDe50XusfaR2tvnO7fwOlFuyWTuQGlM8qf16thj9WwxEgfl/34RqkqKKG9EE1JwluREtQPA7QvD7lyT4w0sSfP9+lirTZf5oFpn3P2dWi5J3vxvDlI/OSLvfg61zNN2ZqunDdOyMph/9r+lCTe9ftKZzb6RU61mOYUepe6nGPTXw1JJ7ad6Y04J4CqRgM9cqd13LJf4/CQ+YYYMbXhU8kP2bo+uujKc5OxWK7/mb0+/5aR7MWvOcYDlLcqUy13nEf4uxjh3ioeQ3uJv/Atcjv0o=
