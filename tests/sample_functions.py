def call_a(x):
    return x * 2


def call_b(x):
    return call_a(x) + call_a(x)


def call_c(x):
    return call_b(x)
