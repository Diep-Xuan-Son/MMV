
import time

def run_test(name):
    stop_flag = True
    print(f"----running: {name}")
    while stop_flag:
        for i in range(100):
            print("running")
            time.sleep(2)
            # if i == 10:
            #     stop_flag = False