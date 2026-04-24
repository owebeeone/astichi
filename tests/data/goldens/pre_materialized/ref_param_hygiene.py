astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    from types import SimpleNamespace

    def consume(class_name):
        return class_name

    def generate(function):

        def wrapper(wrapper_params__astichi_param_hole__):
            return function(astichi_hole(function_params), astichi_insert(function_params, astichi_funcargs(class_name=astichi_ref('cls_ctx').astichi_ref('class_name'))))

        @astichi_insert(wrapper_params, kind='params', ref=Param)
        def __astichi_param_contrib__Root__wrapper_params__0__Param(cls_ctx):
            pass
        return wrapper
    result = generate(consume)(SimpleNamespace(class_name='Counter'))
# astichi-provenance: eNqFVk1vG0UY3tS79vqjcUjVhAKhQQpKKKIgoAHBAaJAK3AxVSqklqpaje1xZuv1jrU7GzeHSly4jcSB5cCJP8ClfwAJiR/EiTPvzM54xputG8mx5515n+f9nvnJ++3njiP/eA2lLOf17+goi3D+a/7OSf4sP+DugI7O88f5AXG4+/XTWWK2vDMUZTgXG8coiiydcRYPpbyPphbWpXCU8w7whEMSBoQCD68N2VN59C5FI310wOtRGOOY5r013sLxKLCWQxoFdDxOMct7Dl8Xu7borWzAXZScpmA02SyYyVW+FQSaOKGUBcGJ/J+TbXKt4CRv9NbIDnze7DnkusBB3J/g8zlNRhLswr6UiJWQFhKHt2+D8yyk8Vd4bIUkFpEge2QXjjTBvGyKY5aaA+0ZTWkcnWvLdx9DMs5QAuu8z1uTubXJ25N5MMJjlEVMrr3JvDjnW1Kwxivy1vpmOqMJu53QqSGsT4tMc4+dz3AK38JEye1wD0UhMtaR93j3fjidRVgkNJ2hIejVUSqd6qswbJowIO5F+AxHkKCKGN1YgDaGNE4zEZhd8r6Sflg4T0RFgk8Le+UKsh+hNA0kMW+hOKYMiWCD7x3hB5TCVERWWuUCcQeIXSDeAqvIrT45BOhP4fNZn3yuYwRc9RPMsiQ2HrdN7ZCHS0XiAWobUD1AvZppiWskiK+P8JAmiNEEChfaClLUSCRBCoY96vO2tHUG6Z2q0nJVkDSqCZJ/imMMYJVR+kGtH3B/rOouJz8KDsD0AfMyYPrKrhf5f2CnZJ6g2Qwnq8n21CnlguktuZatLXpLG9IEQzbAkCYY8vGqRKBF9C+rXxtWHs6W8tAC0C6AtgB0G/R3hSNValug9otSeFUp7BUK1oDo6vjptFhabystafu+zJcNdgvAKoj5uo5KGKc4YXnJ/B0FUgBI843Rv688XMW2odmEI3JSlGab6cIN5f2+rP2GGnKm+B9AydspgJF1xFgSDjKG7RapMqO9GLMw/8CCP4G7Btw+cNeA+4ridrh/DN3PEDSrgYSREKWBvBOE2o5Svd7bN6G30fbltAfbcvJXBdlHiuzvhckPS7h3qnHvyMa+pBq7pg+aMIqZspYNcHU52GJdo4eZrlrfSBAhcPCJ7JOJVGkqTq1iWvOTcpvB9BRJ0XdZuSc/CIJ74ufKVib/LLpUuHZFVcjN1ePSvQdT2KRNWF0UqGu7VdWMfywVZUmt1JLryx7lq1RlEg/I88WIcidhPMoh44vc87rGuUh8UWKQarKSrQuBeyquL3o7OFWIuMroVZlHFVfRMzWVOuoS6sDZTcnWUdpKgi8Ulq8qV6vApXeUpuGpufR4g8HcwKz0dKonOIU3hXAXXgb34VZbDAFB3FW4XcCtC5/suVBVAnQpbkK9qdRfKZcA+Z5sP9lacxx1cFMdvGa61tZ/TelXsX67jPS6UrlhjcLnS+PP1E3jmGYxE3fiv32lfqjUv8i0D+8aCSpxfFlt7RHoPuqXInikU/fy5im/Rpcjt7fyZVvy97+l8nbFPHlZdV9ArBDZ5Vd6BWL1XoP6g3oq3qs3/wdk1Cl0
