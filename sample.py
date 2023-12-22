import time
import tg4perfetto

@tg4perfetto.trace_func
def inner():
    time.sleep(0.5)

@tg4perfetto.trace_func
def outer():
    time.sleep(0.5)
    for i in range(3):
        inner()
   
@tg4perfetto.trace_func     
def generator_inner():
    time.sleep(0.1)

@tg4perfetto.trace_func
def generator():
    time.sleep(0.1)
    generator_inner()
    for i in range(3):
        yield generator_inner()
    time.sleep(0.1)    

@tg4perfetto.trace_func
def main():
        for x in generator():
            outer()


if __name__ == "__main__":
    # Start logging.  Logging stops when this goes out of scope.
    with tg4perfetto.open("tg4p.perfetto-trace"):
        main()            