# While Python's Global Interpreter Lock makes true multithreading difficult, you can use multiprocessing for parallel computation. 
# However, mpmath's computations are typically not trivially parallelizable. 
# For the sake of completeness, here’s an approach using multiprocessing for other types of intensive computations.

import mpmath
from multiprocessing import Pool, cpu_count

# Set the precision
mpmath.mp.dps = 10000  # set number of decimal places

def calculate_segment(start, end, segment_index, total_segments):
    print(f"Segment {segment_index+1}/{total_segments} started.")
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

    # Get the last 50 digits
    last_50_digits = pi_str[-50:]

    print("The last 50 digits of Pi are:", last_50_digits)

if __name__ == "__main__":
    main()