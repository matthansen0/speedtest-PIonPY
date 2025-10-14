# ARM processors benefit from parallel processing across their multiple cores.
# This implementation uses multiprocessing to distribute the Pi calculation workload
# across all available CPU cores, optimizing for ARM architecture.

import mpmath
import time
from multiprocessing import Pool, cpu_count

mpmath.mp.dps = 10000  # set number of decimal places

def calculate_segment(start, end, segment_index, total_segments):
    print(f"Segment {segment_index+1}/{total_segments} started.")
    segment_start_time = time.time()  # Record the start time of the segment
    segment_length = end - start + 1
    ten_percent = segment_length / 10
    progress_checkpoint = ten_percent

    C = 426880 * mpmath.sqrt(10005)
    K = 6 + 12 * start
    M = 1
    X = 1
    L = 13591409 + 545140134 * start
    S = L

    for i in range(start + 1, end + 1):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12

        # Report progress at every 10%
        if i - start >= progress_checkpoint:
            current_time = time.time()
            segment_duration = current_time - segment_start_time
            print(f"Segment {segment_index+1}/{total_segments}: {int((i - start) / segment_length * 100)}% completed. Duration: {segment_duration:.2f} seconds.")
            progress_checkpoint += ten_percent
            segment_start_time = current_time  # Reset the start time for the next 10%

    print(f"Segment {segment_index+1}/{total_segments} completed.")
    return S

def main():
    num_segments = cpu_count()  # Use number of CPU cores
    segment_size = 10000 // num_segments

    segment_args = [(i * segment_size, (i + 1) * segment_size - 1, i, num_segments) for i in range(num_segments)]

    with Pool(processes=num_segments) as pool:
        segments = pool.starmap(calculate_segment, segment_args)

    S = sum(segments)
    C = 426880 * mpmath.sqrt(10005)
    pi = C / S

    # Convert Pi to a string
    pi_str = str(pi)

    # Record the end time
    end_time = time.time()

    # Calculate the duration
    duration = end_time - start_time

    # Get the last 50 digits
    last_50_digits = pi_str[-50:]

    print("The last 50 digits of Pi are:", last_50_digits)
    print(f"The Pi calculation took {duration} seconds.")

# Record the start time
start_time = time.time()

# Ensure to call main() if this script is the entry point
if __name__ == "__main__":
    main()