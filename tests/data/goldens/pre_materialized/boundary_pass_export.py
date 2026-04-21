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
# astichi-provenance: eNrVWM1v40QUd5rY+Wpa7bbd1TZaiaU9pBJavsQBCYTShR42YLTLh8RKq5GdTHfipJ7gj217QOLCx2EEB4w4wJ07JzhwBXHjzpU/gSMH3tjj2B47XUdqhDZSmnrmN++9+b03vxnPp+q3P20p4YdVDdcLmPYOHflTHHwT6Prnwf3gk6DHaiYdnQcPgx5RWO2ts5nDez8TnepjY+rjgHfdMabTcKD+RTzy2LeHYZ9unGSNro1HAVsHn+MhGSNCwSerDr2zEP02NUaAPuBQk2nTsY1tGgzWWAvbI5R6HNIposfHLvaCgcI2eG+6qeObrGY4j1yInuzMnZMb7BpCsW+HUg+h++HfgHTJzcgteWawRm7B99mBQva4KYM1Jvj8lDqj0F6uP2zhT7w1alFY+wgo8MbUfhMfw5R6evTxYoZsTgw5IPuAbUKo/gm2PbcA2Z5Rl9rT83g6+w8hW48NB54DnbUmp6lO1p6cohE+NvypFz6rk9MI10i1QnxalFWt77rjR3Y2eXUPhmAvz13Dpb4zxMjgbClMfc+jDp6nS2KhAbyRDsAad6jteobtpcuAdAYtVpuM7VGgi4HthD627p3PMGT0hJMyR6QJPkoCJncXBWryQO/Nw6sKG9UkvA/SEW2Tj3QBawsYd/VAl8byxma8EMDIZiqWrUwkZDdTVzVhpAZG1sHIvhQ40QD+sQB2BPAKj/S5sO7S46/6ZkHL81L1kJfZXlLxQ2p7ztiMi54vb4ReQKgPVUVekYe+GhUbeU0nr8PPG/Dt6+QwqZ9yHLCN2P34ZEYdT15qSV43iih5F+BfC+CmAG7FlCisLlZmRmOqvOaZalIf6ivM8jzQL6Xlu+2b+RZDCmw7t8a3n1SCVep7i6uvGlVfbqI3M2hNoFtFRdgqXYRJAvBZPgHpCipMwI8A/0UAN5NSK6rJrVxNbpWPcr4nTDCeLdbj7YIY2X5S40aoaAiNQXSgshHiQouQSMdCm/F0imojm/aSK//npWZA/ryc4I4Sm3eLXNxb7KKTT/vi+HOeMdsY4SF1DNgTYKOGIwW4LyUKtovzNXlLVFGkaoU6uRAesfVdgv+eVR3YhMPdqNn3uAT6Hs5setLsWY0rZDaoCnipCC9KeL4ASwGr9GVYxEslghWFl29idQd7vmO7sNc90Fk73P5msMefiBPHJej8iwgdrlLnyVfLCbtJutZLFUVZpO3pBJIf/hcVDxdBeQU3V6XgkpiUkWzrw4jaFas2+eOShPrwKRFqa8p5XbVWx15WJ9fknwv1mfx72YLcyyqyCmc27EiHMxDNvK98S9qQ1eRMdaw2/CyUc+uqnDRJzK0dALDK4ZJSjgvmat3gkcBqt3bhn0LxvvDgqMICiN6wkuSrwoAKBtQo+WUOUjNYYtkZcUMNYWjRMcT6PVIOjt0R2N2yoqyGA7iTvUHXN/MthhRFN1bG9By7pUiS3u40YUArQ5L1m1wRmghKu3jhW39H7GiCHW0ZdrRwQJodqcWQApmzk57cE9nRHOzCq36WnrqwUAcLWvxurr7vz+RLHxxdEvSys/9V5ovbawl7mxBRBv1XxJW6FnLFoVcE9BpfNZmepui5Hs81Hen1paVKvpvJlfjBhVc9uTwKgVlOT4oM55sKpEK65sDiJgQ2SgpJDe9ubv8H11hlQA==
