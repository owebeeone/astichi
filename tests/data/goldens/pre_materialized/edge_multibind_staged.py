astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    left = 10
    right = 20
    records = []
    astichi_hole(body)

    @astichi_insert(body, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__0__Pipeline():
        astichi_hole(__astichi_root__Root__)

        @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Root)
        def __astichi_root__Root__():
            astichi_hole(body)

            @astichi_insert(body, ref=Root.Pipeline.Root.Step)
            def __astichi_contrib__Root__body__0__Step():
                astichi_pass(records, outer_bind=True).append(astichi_pass(left, bound=True))

    @astichi_insert(body, order=1, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__1__Pipeline():
        astichi_hole(__astichi_root__Root__)

        @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Root)
        def __astichi_root__Root__():
            astichi_hole(body)

            @astichi_insert(body, ref=Root.Pipeline.Root.Step)
            def __astichi_contrib__Root__body__0__Step():
                astichi_pass(records, outer_bind=True).append(astichi_pass(right, bound=True))
    result = records
# astichi-provenance: eNrtWUuP21QUdhPHecyDmaEdiVZIDKXpQMXQLhALxGM0LSrKYEFnwYJWlhPf5DpxbGNfd5oFEhsei7vD/Ir+Gf5C12wRC1iUc+3riV/xOJmMOqiNNBP5+pxzz/3O67PzY+33v64KwYdWVZf4VPrK0jwD+b/5svyz/8D/wd+lYtfSJv4jfxcLVLz3xHbY3Z/4zdpj1fCQz24dqIYRKMq/RJp9z+wF92R1nDRa0TWfrsKeeg/rCrZgT1rtkSeB9KGlaiD9LhOlm0ok5To9pa8zyZ2BZWjs+gOkDZAy9gyid3UTlog6QNqePfHdLpUM3USm5XcqtNWzDMXq911E/I5AWwhkp3fX2WVcoonfwjtel4qqM3Dh6PjKief4DbqtnLjkWBZRlAfBfx9fw28GPjNtt4vf7lTw9Y6A34HvG5FNlTZGaHJsOVpgOFdmxqpAV74AQIlumXdRHwDalcMPifA2Gcz4Fm6DbBN898bIJG6O5IptuZZpTKLztR9B7B+rDlz7Mm2NjmM36croWNFQXwWUg+va6DiUa8RWwT8pzBFp33X1gZlMhToBFUSyYIoG6hMGnUBrR8RyUBT4XBBFDiJeA/nGgWVCwE0Szyy81mlRcQTJ4MtcuZ7Eka6SiY0g3mOGzolUGu37U+/xYdrrmqMPcOD2UdLZKrdUBUu1qbPfxv27jL+TuWiDi7b4pg/llI1WGW/qDuoFCZX1R+S2RLBVj4MnHuouSdY5CiOZTWNmpMWNrMY9jVuPbjSj3gDbvBbz+vWEz/hqdpsat1aLWWunzoqlfL01rrcZnXEvKK64ya2T4spbvZMqEfwhfW9a5z3LJI7ejUqddURFua0oX+s2Yn0EKgh/lLbwcVhY+FMZfwZf+/B3IOO701pZHKp4wm7NgGrBPrWVRDBvp/zVLIL46QuEZZ4MqvAMqmQz6Cznp+3TM+iIIHuR7ClACXr/PmGbeQQlunAhntNpbKuu6y8I7vfF4F6OgyvQOh+FiT5UZcOFtizw3lHYVPdTDfTXsH8yuzvc7o1EZLaTq2rK+fbJdAeUYO6pto3YLoUnfj924oKk/DNrhbVzkbfzjVm4fZOvt8n1rsRx+3uq+A+tdS1vJkTxrW963eyKml7KT37W3y9lkj+2qtJ1jc0gFSY4ECuYLIUw0fUo13TTRQ7xF+tws0o5t5UlUKs6QKAAs2eJ4ii6SpIWVsQlnX5OG9MpUU5j+MklQShrXQw7SCnp1Gq2NCLEGKUgnmO6QI8eynQlYEw28MNxDmvlSmh4DdwujPvweumDZWL9dMFYD2+zPcsHdx7wh5/PIVvebukwDe+DTRah4Zch9EsOTB5RKsvIUnplA1MiFHlezQpFCQIYwpvncg68S6KOdy42dZyr2F5xxDOd/4/lkr9nJeleHlNZOsOLlzv+93xoHJS+cGpnPWf2pi3I3obbYQt8odTtfMe2dI5j+0IP8efDe/+/gf+Kib0kTGw39RQJD+HIST9FQosIelH5t2gXk9+hs/G7wnevkoNcz8h7FSxxUxKYkqavXk8bpkytydU24i9b4/Y2llnozVn5dKvcLxozC33OYi789UOdsXxK4XExxF/66wPTgoAFv1fs/QfnXKTQ
