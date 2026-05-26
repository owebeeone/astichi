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
# astichi-provenance: eNrVWM1v40QUT5vYTZOmVTfZrmi10n5RFa3U3T0gDkigtgtCymKJLRIHuho58aTjxPVE/tg2ByQufBzmBOYIEtz5F7hzhBP/Av8DB97Y48R2xo0TulQbqU08896b937ze++N50vlh5+2SuGHlXXXC5j6MTV8CwffB5r2dfA8+CLYY5UONUbBi2CPlFjlg4uhw2e/EpPKS93yccCnjnTLChW1b2LNnm93wzlNP0sbXTaNgK3BmmaXmIhQWJOVu95FKP2M6gZIv8VF2SaKpVyni3oml7xzSi2DPz/qUN82dGeEhrrrInwxpI63PxwFboeplmljmwbtZVbrUgvRXs/FXtAusRq2DTSZXeePSYkGuUPu+h1W0Z1TFyInN8eOkzfYFhp75FDqIfQ8/B+QHXI7dJlrux1yr71M7rdL5AF8vxnb1Fl1gEfn1DFCw1KZnNESq38IeHomtZ/iHuCzp0UfL4bb5iiTh2QXZFfBd/8M254rkawPqUttaxTHt/sCtv6l7sBzoLHa4DwxyeqDc2Tgnu5bXvisDM4juWpiFPxTI4qoB65rntppJqx4oIK9aTCrLvWdLkY6h6/ElGOPOjjeeymQVQEkaYB89YjarqfbXpJcpNGuscrAtI1AE8r1NJZszRsNMez5GUdoLJVF/KNJBORZnucd7vlx2t+yMFZO+/tZ0sUW+VwTonUhGq97omVsxBOrcd6BsY2Ec82Ua2R7mooVYa0C1taEtd1MSESV6zWE3mYcyX7I3KTJG2PmykafZPhH3mb3J0nUpbbnmJ04j3i1QegxQgfAS/JOVvXdiK7kPY28D18H8HekkacTBhbDiK3Hy5tnvGbMyN71PMg+kettCL1mErISWxG5nyqFZZ5NTAkrWZBhybcRSZKutKYKRIsvkBmSVpJWEV6Xqe/NoHR5QulZYHA1VajV8uhdm4vek62Lyn1wOdtzt+5Xud5GmrwytjelbG/OF8W4+Q0wHs6gXysnBvZgkkZ6WHYRMqEgQvIgxLsBQmI3ZxuPAy1Oo4LV6LfFYiN/vSK3L2N/uOhxgUUbM7kkW/pEk09gtm7gLnV06H5wMIGTGPhVqHjZLp6ZATfmrPclWQb8OFH8mZUdOICEDXj1wOPF2/dwquFn8GEVXtuLuQmnLjAZsKWDgmFlRqNiKIuDrTjY8x3bhYZ/orF6eAYYwqnnTJzFrqh3PUHo8FX2LvLdgs3KmKNZJfeb/HLtbSnMsAVakvG/tCRZjXsNehD546rbzuFr33b6F0ul0jV0nnjda2g+5J9Lu02/IkXkqjvMXrrFKHBMxk72PNxeiipP8XePpNH+Jo+k0W/CV26v6m8XDbd/GyTZ0uGifQrnoNG/y/2D/erfgx+5nenSU7wCCRi9VGcIpQhLClhSJoQqclDlVyySWLnFqrA4z2GO690Uetvztp7kojt+Z3pEzw4lsyAJwk5hOGVv+qqwpBaFs/+nlF6qcFWdvzSpAkd1ERyT60Y4Zkb07FASx2T0hXBUHez6luz9ckWYWgFTavKKR/nUH2ZvJHF06bSXhud3KTzccE0Y3hA+ptT+zlXbFGpbcaGUSq0KqVtJZJLh3PpPdVZ2MTWVXg+LXT5O0UJUxCIFsPBFpZ4zLClrEjEs7ubgUEGBLOHV4v6/sNJMGw==
