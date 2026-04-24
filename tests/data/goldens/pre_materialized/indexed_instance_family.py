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
# astichi-provenance: eNrNWEFvG0UUXsdex42TiMakFRJpcwgirRpIjBqhthIqhaqSwUgNEhIoWq3tcWfjzc5qd7ZODggEQgpoDiAW7ohTT/AfeuBPcOFf9Mib3VnPeHeS1HEUNZLj7Ox789773ve+2c235m/PLxvJDyvbIY1Z9VPSi1wU/xrfeBx/Ha+zSof0DuPdeB0brPLxgR/IW+ZT241QzG88sF1X8elHXjdZb9v7yl4zTi9m8xDH6WLHwgTisHKXHiSmnxC7l5l2WNV1POSRuDXD5pDXs5TLLnEt0u+HiMYtgy3yu+pSPeqwih08CSFpvJRGxsvsimVlgQNCqGU9Tn7H+Cp+I42J32zN4BX4XGsZ+Drfx2a1ATockqCXbFa4n6zwK76arhis/hCKpw7xPkJ9BRKPI4HX8CqYXIL0on3k0VAa1H0SEs89zDJf3YVmPLUDuI7bbG4wVG6y+mBo9VDfjlyaXJuDYWpXU1YhGzPtW/V+GDpPPBlsloI5ojmIqgEKwZdDYjBzh5Jg1Lt8qVUAB9eTtjlAG1kmSmPnUL3WuiQxYvP00EfQs30OQdzWoFgTOdXxgvjrNZknvjK2e1n4lsF3HnxX1ZqwCbZfCqsFYXWZJ/920lDVeSnqaFZuiq022A3JoC7xaOB0MhLxEbGsTcvaociHb+geflf4NdNe4tttvA1f78PnThvfzdqjLRUYcp/yABGV06MHQ46Tb4dhEfcM1SIyD8H2QFgtCKtGhozBZgXzZW/LnGJsjkBSgdVxvF6cMKD2gHghtT2qZHrEKgNukPV2Vey/NpqZZbli51J9KxlgqB8GwPZ9xAPJVDOrW6KgH7KYrBoC+hubMT7Kwm4I29uy4eoW24UJ3uYzv9hDXRLYQH9QHSA3+OmAX8yAd7wQBTTOkXJFMCllUZGUx9qmmX4jjL9j5QB0JEHa/DzyFWnGn/HplvVXOBl5jSXYsCQ2NCC4NJnlBP1qc1djhcZyKglQSmILTZbFJTYbIBoFXgh932mzejLmPkjYvpDPs8/WlpitrUlma107XP6J2jKccIL+OW6CRg3E30OoUQuOJDsnHQr8I/5JiXjaIGxNOQjnJ8LMRAc0sPmE/JuT4iW9FDcKUtwYo8stDV0EPywrCZbI8SPk+iiYVo3PlzAvLpwwL04lzHxKmA3RpgJt7uppc69Am3vc8Ge9YOLfj1W9RgGp/06yzeP1B+D1p1YT8bOXkMOt3ZNFs5rRaCrNbBQ1M1n6i2sl/ls3AugMUJ7lsFlXThsTjnxeq8JAKKgYo7gyfT/2VkqGMfXJhHRVHofyZKdQU6hM03qlNGXvixS3C5UVNehpR1Fz2meyix+Evfd4eeoUzFzQFAhVap7DQ9rEo/CBSOLD8eO773i2y4/vR6PYFeFZAU8zfRnUPSSbNHlkHUubu9aE64KWz7+k1OKGi8LwdUkX1X8Z/HfauXyWX1468y/047msnfjPAc0pJF2f5To13mzNZpoltVO5N2QkXqLhrR7e0tO3/Xf+B8O6pR8=
