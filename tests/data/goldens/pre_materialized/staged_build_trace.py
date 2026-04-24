astichi_hole(__astichi_root__Root__)

@astichi_insert(__astichi_root__Root__, ref=Root)
def __astichi_root__Root__():
    trace = []
    astichi_hole(body)

    @astichi_insert(body, ref=Root.Pipeline)
    def __astichi_contrib__Root__body__0__Pipeline():
        astichi_hole(__astichi_root__Middle__)

        @astichi_insert(__astichi_root__Middle__, ref=Root.Pipeline.Middle)
        def __astichi_root__Middle__():
            astichi_hole(head)

            @astichi_insert(head, ref=Root.Pipeline.Middle.Head)
            def __astichi_contrib__Middle__head__0__Head():
                astichi_hole(__astichi_root__Root__)

                @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Middle.Head.Root)
                def __astichi_root__Root__():
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.Pipeline.Middle.Head.Root.First)
                    def __astichi_contrib__Root__body__0__First():
                        leaf_tag = 'leaf-a'
                        astichi_pass(trace, bound=True).append(leaf_tag)

                    @astichi_insert(body, order=1, ref=Root.Pipeline.Middle.Head.Root.Second)
                    def __astichi_contrib__Root__body__1__Second():
                        leaf_tag = 'leaf-b'
                        astichi_pass(trace, bound=True).append(leaf_tag)
            astichi_hole(tail)

            @astichi_insert(tail, ref=Root.Pipeline.Middle.Tail)
            def __astichi_contrib__Middle__tail__0__Tail():
                astichi_hole(__astichi_root__Root__)

                @astichi_insert(__astichi_root__Root__, ref=Root.Pipeline.Middle.Tail.Root)
                def __astichi_root__Root__():
                    astichi_hole(body)

                    @astichi_insert(body, ref=Root.Pipeline.Middle.Tail.Root.First)
                    def __astichi_contrib__Root__body__0__First():
                        leaf_tag = 'leaf-a'
                        astichi_pass(trace, bound=True).append(leaf_tag)

                    @astichi_insert(body, order=1, ref=Root.Pipeline.Middle.Tail.Root.Second)
                    def __astichi_contrib__Root__body__1__Second():
                        leaf_tag = 'leaf-b'
                        astichi_pass(trace, bound=True).append(leaf_tag)
    result = trace
# astichi-provenance: eNrtWs9vG0UUdmyv48ZJRBNRCPRHRIMSgkoBCYTggEIhipTWQk25IFWrtXec2c1m19qdTeoDEgcOCI3EgeVv6B/Bkb8ApAo49UZvSCCVCxfezI69sz9ie2PHSdRGSmLPfjNv3vve+96M7K+VH7+4XuA/tKR5JKCVO47uWyj4IXjjbvBVsEbLDUfvBPeDNVyg5c8etN3okXKgWT4K2INbmmVJc1q+3eTjdW1fWqto6AGdBTtGExsqdsAOLTXJAw697Wh6F9qgFcuwke0E20U6g2xdld42HUt1Wi0PkWC7QOfZU3loxm/QsubuerBpvBBaxi/SS6raNew6DlHVu/xvgF/CS6FNfHm7iK/A79XtAr7G1tFodQ91Dh1X54ulnvMR9o6NhiMFWtsE54nh2J+ilhQSm0UCr+BlgFyA7fn7yCZeBKi1Hc+xrU5358v3gYwDzYX3QZ3O7B1KD2lt71DVUUvzLcLfK3uHIa4qjcJulJC3yobnGbt2ZGyaAByRRIgU4mpNxCJSoMoOcdwedUlPFYgNrnHWDMiayEsUmk4E9ep2NQoRnSWdNgLK9lkEgnpGEKtiSzU8J169EG0TX4qtXhJzSzB3FuYuyy5hBbBfCtScQF1km1/lfMqTF/xGxsi6WOoGXY8SqOnYxDUa3RxiFaKqb6vq50YbsUQF9vBNMfHdkEv8Xh2/D/8+gN8P6/ijiJ48zsr5t5B0lr6cTPE7hq5bqF+SL0SxSK4dpyUWC3xwcg5GJlNs0jJGoBEw4TsBnRPQi7Ib8U33cYOuZVDajRkzxUnd4jZPhdDcmnVMOh+eCp28OH8aD5Org4tz03BBqvJ4+rEAfhIjpWohraUSbZfRsJXparUrj9Vbju0RzY4kEtegtcECN7SAlvcMW+8JYE1MXgTzO0lVXDxCFaGXbBDmrk+QZCOLmqjxtjXPC3KI6CZgnyREtJdpBTotemTUBkqsGVGl4fjgH+zmUXdf3/JVrgh7oVupES2xoUXe0MFLaIhau41sLgFPEqhXUtv+RUK9KlDXs7V/JaX9MILovI6ajqtBJ4TzByQPzMsK7Hw3sIbtIZcEw1c4L4EBpfyXAP9NSy6cKCCcj3s0D/tKklBWFfEdToHVKWG1ADt8SqtRI+sPrIRqOQhW3hK63QdkLk0VCgPWUUQNx1EhaVMClRHF9BCddhHxXduD6tup0xo/kbThsLXfO+jl6Rmy0ryjqjuQNbY+utTwDO6rMI8SotII8B8j6cnjvuL+Zz7RMG8zSo/QjV5a43/GoRD4Kf43brGvMMjAY2kD/i9bDMypZBqPKgBrkgIoILPIjUkqJH52s4+P9NYwZ9kGRxKRIUrVvDwYcm0w5LXBkCFko9ItyFy6gTL4MNfBGpMM8014kaUUY0uMhzk6Q15Ozw2Tx5D2CVL0/dgpOhvEnEjUx3epp2WiGRZUs/lrur8c83Lf7ybIrPEbxD1u9jRugsOowXm58pnFImdt9Fsf/nmSRyz8+5k6W71enPTZSrLY/2wlAc/42ep8HotoOVSiUQ9G5uqktL9XsuZNZnKCVWtuMINnqXA7Ey/czrCF2ymew0uRaYSV+2zciO4Vx3AjMr/JXfjPb0Onz+Jp34ZkwUlRZP42AH5eLkQZ3CQDn/IsPZQR+MTtY2y1cTCm2phArM90BifaTt70HTV8J5JkR3yGVXGR51sk/glWWUwtw9RKeIyKfwa0FINeEND57lFKnj9/7PyeSdGy0vcrGtm05CAjY8n00IAsnGGfFoXfazB2bQeiy79/8db/h7HJJw==
