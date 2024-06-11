#Intel CPUs often benefit from Just-In-Time (JIT) compilation, such as what PyPy provides, due to their high single-thread performance and advanced CPU features.

# This script should be run using the PyPy interpreter to leverage JIT compilation for improved performance
# pypy3 -m pip install -r requirements.txt
# pypy3 intelPi.py


import mpmath

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

    total_iterations = 10000
    breakpoint_interval = total_iterations // 10  # Calculate the interval for breakpoints

    for i in range(1, total_iterations + 1):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12

        # Check if the current iteration is a breakpoint
        if i % breakpoint_interval == 0:
            # Approximate the progress in decimal places
            progress = i // breakpoint_interval * 10  # This is a rough approximation
            print(f"Completed approximately {progress}% of the iterations.")

    pi = C / S
    return pi

# Set the precision and calculate Pi
pi = calculate_pi()

# Convert Pi to a string
pi_str = str(pi)

# Get the last 50 digits of Pi
last_50_digits = pi_str[-50:]

print("The last 50 digits of Pi are:", last_50_digits)