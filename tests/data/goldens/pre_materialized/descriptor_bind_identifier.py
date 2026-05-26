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
# astichi-provenance: eNq9V82P20QUD5s4m4/NVmUJVYuQCt0ui0oXUAWtBAItW7gETFUOvVC5jj3JuPF6LM+kuzkgISG+pLkghj+DAwf+CI7cOYA4I5UTHHljj2NPYme9i9RIUeKZ957fe/N7v/fmc+OHt8/X4g+v25QJ3vyIuFMfie+FaX4l7orPxC5vDIk7E/fFLq7xxvvHYSR3v1SbxiPbnyIhtw5s348Vza9TzdE0cOI90z7Uja55ruAb8E7PwZ6FCbyT1x12HEt/SGwXpF+Wovy8lUrRyLFGnpTcGRPflc+vuog6kRcyEllDL3Atz0UB80YeivbCmaBD3vS9AAVEDNZ4xyG+RUYjipgY1HgHgXy2uykf8xJdfBm/MB3yhh2NKcSP+3P38UV+yZr7FRHCLOuOFyJpzbIEfg4/HzsvLdAhfnGwhq8Mangbfq+mdm3emqDZEYnc2HihTMlqjXc/gMwyjwS30QgytWsmH5YmPpD5xtfwDsi2wf/pIaSFFkh2Q0JJ4M/SGHfuAwge2RE8C5N3Jke5Td6dHFkuGtlTn8XPxuQokWvlVsG/pgRLO8UI7uFzGSjwlp7HOQYmCIWFmdtWOcji31k8jCbFdoTcauo23lP5XrZclu/mPqXeONDhvc4gesSWsdGMEIVsSHdq3PgEwIlSOBciopk61ovR70ElagWIkswWw6qtO8s32CxEAORDeeTCLAmp2ungS8vvrCtrdbC2UXYghoN8n4pi7Z7Sflo/j7zhrfl5FK2+voBi/AZ/KStHhwQs8oaWdTeuy9gTy3rNsg7gHyAc31xUfysBPn7HxO/Czz58D0x8+7RYxncqFf5StvC9aoQxx21Vnvg05+qDFTUzrgjN1gEJKLMDDZ64N+jwxgTIdw62BUhi+v9QyDfTo0XHIYmYWA3KzbI0/1isd07p9cvh+GwhHNUq4psuckhkyybky+IF/SrReAFFJ0azVRbNF5X0kmhqfF31Go1Y6pK9eT2CHhKfb3ufycqZMqQRHez9qT1p4bTSxlctEGin8BLBG7I6K8b+GIaLuHYrSS+syhwUp4avR4hNo4ACcKnJuzFxhtD7DlVHLrJ+duJsKGuNVcTZBvai0K2jIvJsKPJsZOBL0Zo3fmGeiKLVAvK8UUCe2Tgz9yghUfX0pIm0Hp9D0q1vnYJIC/SyCl82qR/6rRMPXS+MKnNOaFMqztZWMVrdULWa/y1T/J13CBR1MiLLUv8px97f4J9NZeeysrOtJaOvry5W09V5kTbtMESBe0Jwr+SCg+noPS/4OFy4NvhoxKqc7JXBdWX0hiKXNRJKq/V919UnLm5E3hiD1XzoAyOL/U1l6aYW+3V9tag3rEQOwr+sbAb419U8caEECQ/bT9VqlVSXwYD/WCL0cnrHf1Vz8DH+u6JgMkUkFFJJY2E1QWBhpP9IHsf/LhMiv5hdIh0CLC8vG5a8JFEI8t53osrAZIy8wPYL5iVDvcqAVxnZvLSCDAw2Df2ihilNtZSp3ilYQOptKr1ndKzmTfbzA1ne7f7Z4Vppwr12igl3Casn4bHyQGyXLeeBowk8/BbqLIcQpK5XcBeES11y3d37D6a8wQU=
