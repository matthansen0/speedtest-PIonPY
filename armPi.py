# Uses the ``mpmath`` library, which has built-in methods to calculate Pi to a high precision.

import mpmath

# Set the precision
mpmath.mp.dps = 100000  # set number of decimal places

# Calculate Pi using the Chudnovsky algorithm
def calculate_pi():
    C = 426880 * mpmath.sqrt(10005)
    K = 6
    M = 1
    X = 1
    L = 13591409
    S = L

    for i in range(1, 100000):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12

    pi = C / S
    return pi

# Set the precision and calculate Pi
pi = calculate_pi()

# Convert Pi to a string
pi_str = str(pi)

# Get the last 50 digits
last_50_digits = pi_str[-50:]

print("The last 50 digits of Pi are:", last_50_digits)