# Uses the ``mpmath`` library, which has built-in methods to calculate Pi to a high precision.

import mpmath
import time

# Set the precision
mpmath.mp.dps = 10000  # set number of decimal places

# Calculate Pi using the Chudnovsky algorithm
def calculate_pi():
    C = 426880 * mpmath.sqrt(10005)
    K = 6
    M = 1
    X = 1
    L = 13591409
    S = L

    for i in range(1, 10000):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12

        # Print a progress message every 1000 iterations
        if i % 1000 == 0:
            print(f"Progress: {i} iterations completed")

    pi = C / S
    return pi

# Set the precision and calculate Pi
pi = calculate_pi()

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