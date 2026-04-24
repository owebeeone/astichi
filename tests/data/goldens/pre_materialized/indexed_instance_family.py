astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    result = []
    astichi_hole(body)

    @astichi_insert(body, ref=('Root', 'Step[0]'))
    def __astichi_contrib__Root__body__0__Step_0_():
        result.append('step-0')

    @astichi_insert(body, order=1, ref=('Root', 'Step[1]'))
    def __astichi_contrib__Root__body__1__Step_1_():
        result.append('step-1')
        astichi_hole(extra)

        @astichi_insert(extra, ref=('Root', 'Step[1]', 'Helper'))
        def __astichi_contrib__Step_1___extra__0__Helper():
            astichi_pass(result, outer_bind=True).append('step-1-extra')

    @astichi_insert(body, order=2, ref=('Root', 'Step[2]'))
    def __astichi_contrib__Root__body__2__Step_2_():
        result.append('step-2')
    final = tuple(result)
# astichi-provenance: eNq9V91u2zYUlmPLceI46OIlwYC1zUWGuUOzJQY2DG2BIetWFPDmAc2uNgSCbNOlYkUUJKpOUBTtrrYL3gxjsatebS+xF9jNHqMvskOJsmiJDuI4qAH/iDyH5/B83/lovjJft24Y8YuV7ZByVv2eDCIX8T/4nSf8BW+xSo8Mzvkxb2GDVb4984NsynxmuxHiYuKh7bqKzzDy+vF41z5V1lpyBpytQRynjx0LE4jDyn16Fpt+R+xBatpjVdfxkEd4Z4mtIm9gKY994lpkOAwR5R2DrYtZdage9VjFDp6GkDTeSCLjTbZlWWnggBBqWU/iT4638QdJTPxhZwnfhPetjoFvi3VsVhuh8zEJBvFihfl4RDyJ0WTEYPVHsHnqEO8bNFRK4olK4F28AyYrkF50ijwaZgZ1n4TEc8/TzHeOAYxndgDPvMtWR2NlktVHY2uAhnbk0vjZHI0Tu5oyCtmYCW7VwzB0nnpZsGUK5ojmSlQNUAi+oiQGM48oCSbY5bdaheLgegybA7TJtomS2Lmq3uqsZDVia/TcR4DZqSgB72qqWJM51XFD/rqR5Ym3plYvS98y+K6B7466J2yC7U/SqiGt3hPJfxwDqjpvRD3NyCdyqT12J2NQn3g0cHopiUSLWNa+ZR1R5MM3oIc/k37tBEv8eRd/AV9fwvteF99P4dFuFRhySEWAiGbdAxbZth4VCqwgA/QHb6CP7fvQHQKMKGfVkIUyWO0h8UJqe1QJxKohbGRvn7PKyIEFUojWpfdWVkB10e1CR2yLHlofoD4JbKATdDGQBfw0qLL1tLiOF6KA8hzINyUyCSpFkGfaJpkabFm2ckbWsugZVg6gT2Mumz9GviJ9+AfRPc8nRakIsMWeSxCgJAMYkExmsiwI8PP+scYKTeVYkkUqySU0WReH2HKAaBR4IQBy1GX1uI18kIhTKU9X5+6B5O7BPNxtacnrz0tXPMZnMP/PDIo+z7HygOOXixDy+sSFmeiMBrZg6r85idnQS0yzIDHNKZjuamCSuFhWHCyWmcfI9VGwqMr4F9UhO6Z9Owz5TPyKiiuwfiutGtKqmZbjd2nG2SoBcQusntAXSGGC8m8ZujvSe3cC42Y2YucS+WhCpLe5mbsFIq0lRNqT8E0C7kmP+3o6PSjQ6YEw/EUvaPjXmarULBTtv4tsc6XDr6Fef2o1Cr+5hDwdHF8sYtWUXgtpWLOoYfHQX0K78N+61kBXKOVVDoOWQkMTTgSxV4WBsKFijOLI4nicrJQMY+GTAul2OavK850Kbak+bev6tGauQ+HkMKnQZc6F9oLngv3u2XdyW2xPpd7SO6KelIL2NfxTmZt/X8kkvp4+S4eOZ7vioHk8iV2RnhXwNJMbh+6oMmn8v20qbeFak64N3Rl1EibUqki6CMP3M7qo/pvgf9TN5bN5eb3K3xqnc9m98Aaqkf7M9U0OqWmwNYtphlSkctcwJG9qcHWEq2Bypfz0f/+eJo4=
